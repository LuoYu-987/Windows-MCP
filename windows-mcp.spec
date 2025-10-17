# -*- mode: python ; coding: utf-8 -*-
"""
Windows-MCP Cython PyInstaller 配置文件
使用 Cython 编译核心代码，防止反编译
主入口 main.py 保持为纯 Python，其他模块编译成 .pyd/.so
"""
from PyInstaller.utils.hooks import collect_all, collect_submodules
import os
import sys
import glob

# 设置 Windows 控制台编码为 UTF-8
if sys.platform == 'win32':
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except Exception:
        pass

# 获取项目根目录
block_cipher = None
project_root = os.path.dirname(os.path.abspath(SPEC))

datas = []
binaries = []
hiddenimports = [
    # 核心依赖 - 显式导入
    'fastmcp',
    'fastmcp.utilities.types',
    'fastmcp.utilities.logging',
    'fastmcp.server',
    'live_inspect',
    'live_inspect.watch_cursor',
    'humancursor',
    'uiautomation',
    'pyautogui',
    'pyperclip',
    'markdownify',
    'click',
    'requests',
    # 图像处理
    'PIL',
    'PIL.Image',
    'PIL._imaging',
    # PDF 处理
    'pdfplumber',
    # 系统工具
    'psutil',
    'pygetwindow',
    # Windows 自动化
    'pywinauto',
    'pywinauto.application',
    'pywinauto.timings',
    # 字符串匹配
    'fuzzywuzzy',
    'Levenshtein',
    # 其他
    'tabulate',
    # 标准库（Cython 编译后可能需要）
    'textwrap',
    'contextlib',
    'typing',
    'asyncio',
]

# 查找所有 Cython 编译的 .pyd/.so 文件
print("🔍 查找 Cython 编译的扩展模块...")
cython_extensions = []

# Windows: .pyd 文件
pyd_files = glob.glob(os.path.join(project_root, 'src', '**', '*.pyd'), recursive=True)
# Linux/Mac: .so 文件
so_files = glob.glob(os.path.join(project_root, 'src', '**', '*.so'), recursive=True)

cython_extensions.extend(pyd_files)
cython_extensions.extend(so_files)

if cython_extensions:
    print(f"✅ 找到 {len(cython_extensions)} 个 Cython 扩展:")
    for ext in cython_extensions:
        print(f"  - {os.path.basename(ext)}")
        # 将扩展文件添加到 binaries
        # 格式: (源文件, 目标目录)
        rel_dir = os.path.dirname(os.path.relpath(ext, project_root))
        binaries.append((ext, rel_dir))
else:
    print("⚠️ 未找到 Cython 扩展文件")
    print("   请先运行: python setup.py build_ext --inplace")

# 手动添加 src 下的子模块到 hiddenimports
# 因为 PyInstaller 无法自动检测 Cython 编译的模块的依赖
src_modules = [
    'src.desktop',
    'src.desktop.views',
    'src.desktop.config',
    'src.desktop.service',
    'src.desktop.launch_cn_plus',
    'src.tree',
    'src.tree.views',
    'src.tree.utils',
    'src.tree.service',
    'src.tree.config',
]
hiddenimports.extend(src_modules)

# 自动收集依赖的数据文件和二进制文件
for module in ['fastmcp', 'uiautomation', 'live_inspect', 'humancursor', 'pywinauto']:
    try:
        tmp_ret = collect_all(module)
        datas += tmp_ret[0]
        binaries += tmp_ret[1]
        hiddenimports += tmp_ret[2]
        print(f"✅ 收集 {module} 的依赖")
    except Exception as e:
        print(f"⚠️ 收集 {module} 失败: {e}")

# 添加 src 目录（包含 Cython 编译的模块）
# 注意：Cython 编译后，.py 文件会被 .pyd/.so 替换
datas.append((os.path.join(project_root, 'src'), 'src'))

print(f"\n📦 配置摘要:")
print(f"  - hiddenimports: {len(hiddenimports)} 个")
print(f"  - datas: {len(datas)} 个")
print(f"  - binaries: {len(binaries)} 个")
print()

a = Analysis(
    [os.path.join(project_root, 'main.py')],  # 主入口保持为 .py
    pathex=[project_root],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'unittest',
        'test',
        'pytest',
        '_pytest',
        'matplotlib',  # 如果不需要
        'IPython',
        'jupyter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,  # False = 打包到 archive
    optimize=0,  # 0 = 不优化字节码
)

# 创建 PYZ archive（Python 字节码包）
# 注意：Cython 编译的模块是 .pyd/.so，不会进入 PYZ
pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher
)

# 创建单文件 EXE
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='windows-mcp',
    debug=False,  # True = 显示详细日志（调试时使用）
    bootloader_ignore_signals=False,
    strip=False,  # False = 保留符号信息
    upx=False,  # 不使用 UPX 压缩
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # True = 显示控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

print("\n" + "=" * 60)
print("✅ Spec 文件配置完成")
print("=" * 60)
print("\n使用方法:")
print("  1. 先编译 Cython: python setup.py build_ext --inplace")
print("  2. 再打包 exe: pyinstaller windows-mcp.spec")
print()
