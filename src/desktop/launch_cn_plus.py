"""
中文增强启动器 - Chinese Smart Launcher
=============================================

功能特性:
1. 拼音智能匹配 (全拼/首字母/混合)
2. 中文编码自适应 (GBK/UTF-8)
3. 多路径程序索引 (PATH/Program Files/注册表/开始菜单)
4. 性能优化 (缓存/懒加载)

使用示例:
    launcher = ChineseLauncher()
    result, code = launcher.launch("记事本")  # 中文
    result, code = launcher.launch("jishiben")  # 全拼
    result, code = launcher.launch("jsb")  # 首字母
    result, code = launcher.launch("notepad")  # 英文
"""

import os
import re
import csv
import io
import json
import locale
import subprocess
import winreg
import time
import threading
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Tuple, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from fuzzywuzzy import process as fuzz_process

# 尝试导入 pypinyin，如果不存在则使用降级方案
try:
    from pypinyin import lazy_pinyin, Style
    PINYIN_AVAILABLE = True
except ImportError:
    PINYIN_AVAILABLE = False
    print("[Warning] pypinyin not installed. Pinyin matching will be limited.")


@dataclass
class ProgramCandidate:
    """程序候选者"""
    display_name: str              # 显示名称
    executable_path: str           # 可执行文件路径
    source: str                    # 来源: 'startmenu'|'path'|'registry'|'scan'|'uwp'
    aliases: List[str] = field(default_factory=list)  # 别名列表
    metadata: Dict = field(default_factory=dict)      # 额外元数据

    def all_names(self) -> Set[str]:
        """返回所有可用名称（包括别名）"""
        names = {self.display_name}
        names.update(self.aliases)
        # 添加路径的文件名
        if self.executable_path:
            names.add(Path(self.executable_path).stem)
            names.add(Path(self.executable_path).name)
        return names


class PinyinMatcher:
    """拼音匹配引擎"""

    def __init__(self):
        self.enabled = PINYIN_AVAILABLE

    def to_pinyin_full(self, text: str) -> str:
        """转换为全拼（小写，无分隔符）"""
        if not self.enabled:
            return text.lower()
        return ''.join(lazy_pinyin(text, style=Style.NORMAL)).lower()

    def to_pinyin_initials(self, text: str) -> str:
        """转换为拼音首字母（小写）"""
        if not self.enabled:
            return text.lower()
        return ''.join(lazy_pinyin(text, style=Style.FIRST_LETTER)).lower()

    def match_score(self, query: str, target: str) -> int:
        """
        计算匹配分数 (0-100)

        匹配策略:
        - 精确匹配: 100
        - 前缀匹配: 90
        - 全拼匹配: 85
        - 首字母匹配: 75
        - 包含匹配: 60
        """
        query = query.lower().strip()
        target = target.lower().strip()

        # 精确匹配
        if query == target:
            return 100

        # 前缀匹配
        if target.startswith(query):
            return 90

        # 包含匹配
        if query in target:
            return 60

        if not self.enabled:
            return 0

        # 拼音全拼匹配
        target_pinyin = self.to_pinyin_full(target)
        if query == target_pinyin or target_pinyin.startswith(query):
            return 85
        if query in target_pinyin:
            return 55

        # 拼音首字母匹配
        target_initials = self.to_pinyin_initials(target)
        if query == target_initials or target_initials.startswith(query):
            return 75
        if query in target_initials:
            return 50

        return 0


class EncodingHelper:
    """编码处理助手 - 自适应 GBK/UTF-8"""

    def __init__(self):
        self.system_encoding = locale.getpreferredencoding(False)
        self.detected_encoding = self._detect_system_encoding()

    def _detect_system_encoding(self) -> str:
        """检测系统实际编码"""
        # 尝试检测 Windows 代码页
        try:
            result = subprocess.run(
                ['chcp'],
                capture_output=True,
                shell=True,
                timeout=3
            )
            output = result.stdout.decode('ascii', errors='ignore')
            # 输出格式: "Active code page: 936"
            match = re.search(r'(\d+)', output)
            if match:
                codepage = match.group(1)
                if codepage == '936':
                    return 'gbk'
                elif codepage == '65001':
                    return 'utf-8'
        except:
            pass

        # 降级方案
        if 'chinese' in self.system_encoding.lower() or 'gbk' in self.system_encoding.lower():
            return 'gbk'
        return 'utf-8'

    def decode_bytes(self, data: bytes) -> str:
        """智能解码字节流"""
        if not data:
            return ''

        # 尝试多种编码
        encodings = [self.detected_encoding, 'utf-8', 'gbk', 'gb2312', 'utf-16']

        for encoding in encodings:
            try:
                return data.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                continue

        # 最后使用 ignore 模式
        return data.decode('utf-8', errors='ignore')

    def run_powershell(self, script: str, timeout: int = 25) -> Tuple[str, int]:
        """执行 PowerShell 命令并正确处理编码"""
        try:
            # 强制 PowerShell 输出为 UTF-8
            wrapped_script = f"[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; {script}"

            result = subprocess.run(
                ['powershell', '-NoProfile', '-Command', wrapped_script],
                capture_output=True,
                timeout=timeout,
                cwd=os.path.expanduser('~')
            )

            # 智能解码
            stdout = self.decode_bytes(result.stdout)
            stderr = self.decode_bytes(result.stderr)

            return (stdout or stderr, result.returncode)
        except subprocess.TimeoutExpired:
            return ('Command timeout', 1)
        except Exception as e:
            return (f'Command failed: {str(e)}', 1)


class ChineseLauncher:
    """中文智能启动器"""

    def __init__(self, enable_cache: bool = True, auto_index: bool = True):
        self.encoding_helper = EncodingHelper()
        self.pinyin_matcher = PinyinMatcher()
        self.enable_cache = enable_cache

        # 候选程序缓存
        self._candidates: List[ProgramCandidate] = []
        self._indexed = False
        self._full_indexed = False  # 是否完成完整索引

        # 线程安全锁
        self._lock = threading.RLock()

        # 后台索引相关
        self._background_indexing = False
        self._index_thread: Optional[threading.Thread] = None
        self._executor: Optional[ThreadPoolExecutor] = None

        # 使用频率统计（用于优化匹配优先级）
        self._usage_stats: Dict[str, int] = self._load_usage_stats()

        # 尝试加载缓存
        if enable_cache:
            cache_loaded = self._load_index_cache()
            if cache_loaded:
                print(f"[Info] 从缓存加载了 {len(self._candidates)} 个程序 (耗时 <100ms)")

        # 在后台自动加载索引
        if auto_index and enable_cache:
            self._start_background_indexing()

    # ==================== 公共 API ====================

    def launch(self, query: str, force_reindex: bool = False, wait_for_index: bool = True) -> Tuple[str, int]:
        """
        启动程序

        Args:
            query: 程序名称（支持中文、英文、拼音、首字母）
            force_reindex: 是否强制重新索引
            wait_for_index: 是否等待后台索引完成（最多等待5秒）

        Returns:
            (结果消息, 状态码)
        """
        # 强制重新索引
        if force_reindex:
            self._build_index()
        # 如果未索引,等待后台索引或执行快速索引
        elif not self._indexed:
            if wait_for_index:
                # 等待后台索引，最多5秒
                self._wait_for_indexing(timeout=5.0)

            # 如果后台索引仍未完成，执行快速索引
            if not self._indexed:
                print("[Info] 首次使用,正在快速索引程序...")
                self._build_quick_index()

        # 匹配程序
        candidate = self._match_program(query)
        if not candidate:
            # 如果未找到且未完成完整索引,尝试完整索引
            if not self._full_indexed:
                print(f"[Info] 快速索引中未找到 '{query}',正在进行完整索引...")
                self._build_full_index()
                candidate = self._match_program(query)

            if not candidate:
                return (f"未找到程序: '{query}'", 1)

        # 启动程序
        result, code = self._start_program(candidate)

        # 更新使用统计
        if code == 0:
            self._update_usage(candidate.display_name)

        return (result, code)

    def search(self, query: str, limit: int = 5, wait_for_index: bool = True) -> List[ProgramCandidate]:
        """
        搜索程序（不启动）

        Args:
            query: 搜索关键词
            limit: 返回结果数量
            wait_for_index: 是否等待后台索引完成

        Returns:
            候选程序列表
        """
        # 如果未索引,等待后台索引或执行快速索引
        if not self._indexed:
            if wait_for_index:
                # 等待后台索引，最多5秒
                self._wait_for_indexing(timeout=5.0)

            # 如果后台索引仍未完成，执行快速索引
            if not self._indexed:
                print("[Info] 首次搜索,正在快速索引程序...")
                self._build_quick_index()

        return self._fuzzy_match(query, limit=limit)

    # ==================== 后台索引管理 ====================

    def _start_background_indexing(self):
        """在后台启动索引任务"""
        if self._background_indexing or self._indexed:
            return

        self._background_indexing = True
        self._index_thread = threading.Thread(
            target=self._background_index_worker,
            daemon=True,
            name="ProgramIndexer"
        )
        self._index_thread.start()
        print("[Info] 后台索引线程已启动")

    def _background_index_worker(self):
        """后台索引工作函数"""
        try:
            # 第一阶段：快速索引（开始菜单 + PATH）
            print("[Info] 后台: 正在进行快速索引...")
            self._build_quick_index()

            # 第二阶段：完整索引（注册表 + 常见路径 + 快捷方式）
            print("[Info] 后台: 快速索引完成，正在进行完整索引...")
            self._build_full_index()

            print("[Info] 后台: 程序索引已完成")
        except Exception as e:
            print(f"[Error] 后台索引失败: {e}")
        finally:
            self._background_indexing = False

    def _wait_for_indexing(self, timeout: float = 5.0) -> bool:
        """等待后台索引完成

        Args:
            timeout: 最大等待时间（秒）

        Returns:
            bool: 是否成功获得索引
        """
        if self._indexed:
            return True

        if self._index_thread and self._index_thread.is_alive():
            # 等待索引完成，但有超时限制
            self._index_thread.join(timeout=timeout)

        return self._indexed

    def cleanup(self):
        """清理资源"""
        if self._executor:
            self._executor.shutdown(wait=False)

    # ==================== 索引构建 ====================

    def _build_quick_index(self):
        """快速索引 - 仅索引最常用的来源（开始菜单 + PATH）"""
        with self._lock:
            if self._indexed:
                return

            print("[Info] 开始快速索引...")
            start_time = time.time()

            candidates = []

            # 使用线程池并发执行索引任务
            if not self._executor:
                self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="IndexWorker")

            futures = {}
            # 1. 开始菜单程序 (最常用，UWP应用和传统应用)
            futures['startmenu'] = self._executor.submit(self._index_start_menu)
            # 2. PATH 环境变量 (命令行工具)
            futures['path'] = self._executor.submit(self._index_path_env)

            # 收集结果
            for name, future in futures.items():
                try:
                    result = future.result(timeout=30)
                    candidates.extend(result)
                    print(f"[Info] {name} 索引完成: {len(result)} 个程序")
                except Exception as e:
                    print(f"[Warning] Index {name} failed: {e}")

            # 去重
            self._candidates = self._deduplicate(candidates)
            self._indexed = True

            elapsed = time.time() - start_time
            print(f"[Info] 快速索引完成: {len(self._candidates)} 个程序 (耗时 {elapsed:.2f}s)")

            # 保存缓存
            if self.enable_cache:
                self._save_index_cache()

    def _build_full_index(self):
        """完整索引 - 包含所有来源（注册表、常见路径、快捷方式）"""
        with self._lock:
            if self._full_indexed:
                return

            print("[Info] 开始完整索引...")
            start_time = time.time()

            # 确保已有基础索引
            if not self._indexed:
                self._build_quick_index()

            if not self._executor:
                self._executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="FullIndexWorker")

            # 使用线程池并发执行耗时的索引操作
            futures = {}
            # 3. 常见安装路径扫描 (耗时操作)
            futures['common_paths'] = self._executor.submit(self._index_common_paths)
            # 4. 注册表程序
            futures['registry'] = self._executor.submit(self._index_registry)
            # 5. 快捷方式 (最耗时操作)
            futures['shortcuts'] = self._executor.submit(self._index_shortcuts)

            # 收集结果
            additional_candidates = list(self._candidates)
            for name, future in futures.items():
                try:
                    result = future.result(timeout=60)
                    additional_candidates.extend(result)
                    print(f"[Info] {name} 索引完成: {len(result)} 个程序")
                except Exception as e:
                    print(f"[Warning] Index {name} failed: {e}")

            # 去重
            self._candidates = self._deduplicate(additional_candidates)
            self._full_indexed = True

            elapsed = time.time() - start_time
            print(f"[Info] 完整索引完成: {len(self._candidates)} 个程序 (额外耗时 {elapsed:.2f}s)")

            # 更新缓存
            if self.enable_cache:
                self._save_index_cache()

    def _build_index(self):
        """构建程序索引（兼容旧代码，调用完整索引）"""
        if not self._indexed:
            self._build_quick_index()
        if not self._full_indexed:
            self._build_full_index()

    def _index_start_menu(self) -> List[ProgramCandidate]:
        """索引开始菜单程序"""
        ps_script = 'Get-StartApps | ConvertTo-Csv -NoTypeInformation'
        output, code = self.encoding_helper.run_powershell(ps_script)

        if code != 0 or not output:
            return []

        candidates = []
        reader = csv.DictReader(io.StringIO(output))

        for row in reader:
            name = (row.get('Name') or '').strip()
            appid = (row.get('AppID') or '').strip()

            if not name or not appid:
                continue

            candidates.append(ProgramCandidate(
                display_name=name,
                executable_path=f'shell:AppsFolder\\{appid}',
                source='startmenu',
                metadata={'appid': appid}
            ))

        return candidates

    def _index_path_env(self) -> List[ProgramCandidate]:
        """索引 PATH 环境变量中的程序"""
        candidates = []
        path_env = os.environ.get('PATH', '')

        for path_dir in path_env.split(os.pathsep):
            if not path_dir or not os.path.isdir(path_dir):
                continue

            try:
                for file in os.listdir(path_dir):
                    if file.lower().endswith(('.exe', '.bat', '.cmd')):
                        full_path = os.path.join(path_dir, file)
                        name = Path(file).stem

                        candidates.append(ProgramCandidate(
                            display_name=name,
                            executable_path=full_path,
                            source='path'
                        ))
            except (PermissionError, OSError):
                continue

        return candidates

    def _index_common_paths(self) -> List[ProgramCandidate]:
        """索引常见程序安装路径"""
        common_paths = [
            os.path.expandvars(r'%ProgramFiles%'),
            os.path.expandvars(r'%ProgramFiles(x86)%'),
            os.path.expandvars(r'%LocalAppData%\Programs'),
            os.path.expanduser(r'~\AppData\Local\Programs'),
        ]

        candidates = []

        for base_path in common_paths:
            if not os.path.isdir(base_path):
                continue

            # 限制扫描深度为 2 层（性能考虑）
            candidates.extend(self._scan_directory(base_path, max_depth=2))

        return candidates

    def _scan_directory(self, directory: str, max_depth: int = 2, current_depth: int = 0) -> List[ProgramCandidate]:
        """递归扫描目录（限制深度）"""
        if current_depth >= max_depth:
            return []

        candidates = []

        try:
            for entry in os.scandir(directory):
                try:
                    if entry.is_file() and entry.name.lower().endswith('.exe'):
                        name = Path(entry.name).stem
                        candidates.append(ProgramCandidate(
                            display_name=name,
                            executable_path=entry.path,
                            source='scan'
                        ))
                    elif entry.is_dir() and not entry.name.startswith('.'):
                        candidates.extend(
                            self._scan_directory(entry.path, max_depth, current_depth + 1)
                        )
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError):
            pass

        return candidates

    def _index_registry(self) -> List[ProgramCandidate]:
        """索引注册表中的程序信息"""
        reg_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]

        candidates = []

        for root, path in reg_paths:
            try:
                with winreg.OpenKey(root, path) as key:
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, subkey_name) as subkey:
                                display_name = self._read_reg_value(subkey, 'DisplayName')
                                display_icon = self._read_reg_value(subkey, 'DisplayIcon')
                                install_location = self._read_reg_value(subkey, 'InstallLocation')

                                if not display_name:
                                    continue

                                exe_path = self._extract_exe_path(display_icon, install_location)
                                if exe_path:
                                    candidates.append(ProgramCandidate(
                                        display_name=display_name,
                                        executable_path=exe_path,
                                        source='registry',
                                        metadata={'install_location': install_location or ''}
                                    ))
                        except OSError:
                            continue
            except OSError:
                continue

        return candidates

    def _index_shortcuts(self) -> List[ProgramCandidate]:
        """索引快捷方式 (.lnk)"""
        shortcut_dirs = [
            os.path.expandvars(r'%ProgramData%\Microsoft\Windows\Start Menu\Programs'),
            os.path.expandvars(r'%AppData%\Microsoft\Windows\Start Menu\Programs'),
            os.path.expandvars(r'%Public%\Desktop'),
            os.path.expanduser(r'~\Desktop'),
        ]

        existing_dirs = [d for d in shortcut_dirs if os.path.isdir(d)]
        if not existing_dirs:
            return []

        ps_script = (
            "$ws = New-Object -ComObject WScript.Shell; "
            f"Get-ChildItem -Path '{';'.join(existing_dirs)}' -Filter *.lnk -Recurse -ErrorAction SilentlyContinue | "
            "ForEach-Object { $s=$ws.CreateShortcut($_.FullName); [PSCustomObject]@{Name=$_.BaseName;Target=$s.TargetPath} } | "
            "Where-Object { $_.Target -and $_.Target -like '*.exe' } | "
            "ConvertTo-Csv -NoTypeInformation"
        )

        output, code = self.encoding_helper.run_powershell(ps_script, timeout=30)
        if code != 0 or not output:
            return []

        candidates = []
        reader = csv.DictReader(io.StringIO(output))

        for row in reader:
            name = (row.get('Name') or '').strip()
            target = (row.get('Target') or '').strip()

            if name and target and os.path.isfile(target):
                candidates.append(ProgramCandidate(
                    display_name=name,
                    executable_path=target,
                    source='shortcut'
                ))

        return candidates

    # ==================== 匹配引擎 ====================

    def _match_program(self, query: str) -> Optional[ProgramCandidate]:
        """匹配程序（单一最佳结果）"""
        results = self._fuzzy_match(query, limit=1)
        return results[0] if results else None

    def _fuzzy_match(self, query: str, limit: int = 5) -> List[ProgramCandidate]:
        """模糊匹配（返回多个结果）"""
        query = query.strip()
        if not query:
            return []

        # 使用锁确保线程安全
        with self._lock:
            # 计算每个候选程序的得分
            scored_candidates = []

            for candidate in self._candidates:
                max_score = 0

                # 对所有名称变体计算匹配分数
                for name in candidate.all_names():
                    score = self.pinyin_matcher.match_score(query, name)
                    max_score = max(max_score, score)

                if max_score > 0:
                    # 考虑使用频率加权
                    usage_bonus = self._usage_stats.get(candidate.display_name, 0) * 2
                    final_score = max_score + usage_bonus
                    scored_candidates.append((final_score, candidate))

            # 按得分排序
            scored_candidates.sort(key=lambda x: x[0], reverse=True)

            # 如果最高分太低，尝试传统模糊匹配
            if not scored_candidates or scored_candidates[0][0] < 50:
                fallback = self._fallback_fuzzy_match(query, limit)
                if fallback:
                    return fallback

            return [c for _, c in scored_candidates[:limit]]

    def _fallback_fuzzy_match(self, query: str, limit: int = 5) -> List[ProgramCandidate]:
        """降级模糊匹配（使用 fuzzywuzzy）"""
        # 线程安全地访问候选程序列表
        with self._lock:
            name_to_candidate = {}
            names = []

            for candidate in self._candidates:
                for name in candidate.all_names():
                    if name not in name_to_candidate:
                        name_to_candidate[name] = candidate
                        names.append(name)

            matches = fuzz_process.extract(query, names, limit=limit)
            results = []

            for name, score in matches:
                if score >= 60:
                    candidate = name_to_candidate[name]
                    if candidate not in results:
                        results.append(candidate)

            return results[:limit]

    # ==================== 程序启动 ====================

    def _start_program(self, candidate: ProgramCandidate) -> Tuple[str, int]:
        """启动程序"""
        path = candidate.executable_path

        # UWP 应用（通过 AppsFolder）
        if path.startswith('shell:AppsFolder\\'):
            ps_script = f"Start-Process '{path}'"
            _, code = self.encoding_helper.run_powershell(ps_script)
            return (f"已启动: {candidate.display_name}", code)

        # 普通可执行文件
        if os.path.isfile(path):
            try:
                ps_script = f"Start-Process -FilePath '{path}'"
                _, code = self.encoding_helper.run_powershell(ps_script)
                return (f"已启动: {candidate.display_name}", code)
            except Exception as e:
                return (f"启动失败: {str(e)}", 1)

        return (f"程序路径无效: {path}", 1)

    # ==================== 工具方法 ====================

    def _deduplicate(self, candidates: List[ProgramCandidate]) -> List[ProgramCandidate]:
        """去重（基于可执行文件路径）"""
        seen = set()
        unique = []

        for candidate in candidates:
            key = candidate.executable_path.lower()
            if key not in seen:
                seen.add(key)
                unique.append(candidate)

        return unique

    def _read_reg_value(self, key, name: str) -> Optional[str]:
        """读取注册表值"""
        try:
            value, _ = winreg.QueryValueEx(key, name)
            return value if isinstance(value, str) else None
        except OSError:
            return None

    def _extract_exe_path(self, icon: Optional[str], install_loc: Optional[str]) -> Optional[str]:
        """从注册表信息中提取可执行文件路径"""
        # 优先使用 DisplayIcon
        if icon:
            path = icon.split(',')[0].strip().strip('"')
            if os.path.isfile(path) and path.lower().endswith('.exe'):
                return path

        # 在安装目录中查找主程序
        if install_loc and os.path.isdir(install_loc):
            try:
                exe_files = [
                    os.path.join(install_loc, f)
                    for f in os.listdir(install_loc)
                    if f.lower().endswith('.exe')
                ]

                # 优先匹配目录名
                dir_name = os.path.basename(install_loc).lower()
                for exe_path in exe_files:
                    exe_name = Path(exe_path).stem.lower()
                    if dir_name in exe_name or exe_name in dir_name:
                        return exe_path

                # 返回第一个
                if exe_files:
                    return exe_files[0]
            except (PermissionError, OSError):
                pass

        return None

    def _load_usage_stats(self) -> Dict[str, int]:
        """加载使用统计"""
        stats_file = Path.home() / '.windows_mcp_cn_stats.json'
        if stats_file.exists():
            try:
                with open(stats_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def _update_usage(self, program_name: str):
        """更新使用统计"""
        if not self.enable_cache:
            return

        self._usage_stats[program_name] = self._usage_stats.get(program_name, 0) + 1

        stats_file = Path.home() / '.windows_mcp_cn_stats.json'
        try:
            with open(stats_file, 'w', encoding='utf-8') as f:
                json.dump(self._usage_stats, f, ensure_ascii=False, indent=2)
        except:
            pass

    def _load_index_cache(self) -> bool:
        """
        加载索引缓存

        Returns:
            bool: 是否成功加载缓存
        """
        cache_file = Path.home() / '.windows_mcp_program_cache.json'
        if not cache_file.exists():
            return False

        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 检查缓存是否过期 (12小时，改为更短的缓存有效期)
            cache_age = time.time() - data.get('timestamp', 0)
            if cache_age > 43200:  # 12 * 60 * 60
                print(f"[Info] 缓存已过期 ({cache_age / 3600:.1f} 小时), 将重新索引")
                return False

            # 恢复候选程序列表
            candidates_data = data.get('candidates', [])
            self._candidates = []
            for item in candidates_data:
                try:
                    # 处理旧缓存格式兼容性
                    candidate = ProgramCandidate(
                        display_name=item.get('display_name', ''),
                        executable_path=item.get('executable_path', ''),
                        source=item.get('source', 'cache'),
                        aliases=item.get('aliases', []),
                        metadata=item.get('metadata', {})
                    )
                    self._candidates.append(candidate)
                except Exception as e:
                    print(f"[Warning] 跳过无效缓存条目: {e}")
                    continue

            self._indexed = True
            self._full_indexed = data.get('full_indexed', False)

            return len(self._candidates) > 0

        except Exception as e:
            print(f"[Warning] 加载缓存失败: {e}")
            return False

    def _save_index_cache(self):
        """保存索引缓存"""
        cache_file = Path.home() / '.windows_mcp_program_cache.json'

        try:
            # 转换为可序列化格式
            candidates_data = []
            for candidate in self._candidates:
                try:
                    candidates_data.append(asdict(candidate))
                except Exception as e:
                    print(f"[Warning] 跳过序列化失败的候选项: {e}")
                    continue

            data = {
                'timestamp': time.time(),
                'full_indexed': self._full_indexed,
                'candidates': candidates_data,
                'version': '1.0'  # 缓存格式版本
            }

            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            print(f"[Info] 已保存 {len(candidates_data)} 个程序到缓存")

        except Exception as e:
            print(f"[Warning] 保存缓存失败: {e}")


# ==================== 测试代码 ====================

if __name__ == '__main__':
    print("=" * 60)
    print("中文智能启动器性能测试")
    print("=" * 60)

    # 初始化启动器（自动启动后台索引）
    print("\n[测试] 初始化启动器...")
    init_start = time.time()
    launcher = ChineseLauncher(enable_cache=True, auto_index=True)
    init_time = time.time() - init_start
    print(f"[结果] 初始化耗时: {init_time:.3f}s (非阻塞)")

    # 测试搜索（会等待后台索引或执行快速索引）
    print("\n[测试] 执行搜索（测试等待后台索引）...")
    search_start = time.time()
    test_queries = [
        "记事本",      # 中文
        "jishiben",    # 全拼
        "jsb",         # 首字母
        "notepad",     # 英文
        "chrome",      # 浏览器
    ]

    all_results = []
    for query in test_queries:
        query_start = time.time()
        results = launcher.search(query, limit=3, wait_for_index=True)
        query_time = time.time() - query_start
        print(f"\n搜索: {query} (耗时: {query_time:.3f}s)")
        for i, candidate in enumerate(results, 1):
            print(f"  {i}. {candidate.display_name} ({candidate.source})")
        all_results.extend(results)

    total_search_time = time.time() - search_start
    print(f"\n[统计] 总搜索时间: {total_search_time:.3f}s")
    print(f"[统计] 已索引程序数: {len(launcher._candidates)}")
    print(f"[统计] 完整索引完成: {launcher._full_indexed}")

    # 清理资源
    launcher.cleanup()
