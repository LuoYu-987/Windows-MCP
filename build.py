#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Windows-MCP Cython 打包脚本
先使用 Cython 编译核心代码，再使用 PyInstaller 打包
防止源码被反编译
"""
import os
import sys
import shutil
import subprocess
import argparse
import glob
from pathlib import Path

# 设置 Windows 控制台编码为 UTF-8
if sys.platform == 'win32':
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except Exception:
        pass  # 如果设置失败,继续运行


def print_banner():
    """打印欢迎横幅"""
    print("=" * 70)
    print("Windows-MCP Cython 打包工具")
    print("第一步：Cython 编译 (.py → .c → .pyd/.so)")
    print("第二步：PyInstaller 打包 (.pyd + main.py → .exe)")
    print("防止源码被反编译")
    print("=" * 70)
    print()


def check_cython():
    """检查 Cython 是否安装"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", "import Cython; print(Cython.__version__)"],
            capture_output=True,
            text=True,
            check=True
        )
        version = result.stdout.strip()
        print(f"✓ Cython 已安装: {version}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("✗ Cython 未安装")
        print("  请运行: pip install cython")
        return False


def check_pyinstaller():
    """检查 PyInstaller 是否安装"""
    try:
        result = subprocess.run(
            ["pyinstaller", "--version"],
            capture_output=True,
            text=True,
            check=True
        )
        version = result.stdout.strip()
        print(f"✓ PyInstaller 已安装: {version}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("✗ PyInstaller 未安装")
        print("  请运行: pip install pyinstaller")
        return False


def check_compiler():
    """检查 C 编译器是否可用"""
    print("\n检查 C 编译器...")

    if sys.platform == 'win32':
        # Windows: 检查 MSVC
        try:
            result = subprocess.run(
                ["cl.exe"],
                capture_output=True,
                text=True
            )
            print("✓ 找到 Microsoft Visual C++ 编译器")
            return True
        except FileNotFoundError:
            print("⚠️ 未找到 MSVC 编译器")
            print("\n请安装以下之一:")
            print("  1. Visual Studio Build Tools")
            print("  2. Microsoft Visual C++ 14.0 或更高版本")
            print("\n下载地址:")
            print("  https://visualstudio.microsoft.com/downloads/")
            print("  选择 'Build Tools for Visual Studio'")
            return False
    else:
        # Linux/Mac: 检查 gcc
        try:
            result = subprocess.run(
                ["gcc", "--version"],
                capture_output=True,
                text=True,
                check=True
            )
            print("✓ 找到 GCC 编译器")
            return True
        except FileNotFoundError:
            print("✗ 未找到 GCC 编译器")
            return False


def clean_build_dirs(clean_cython=True):
    """清理旧的构建文件"""
    dirs_to_clean = ["build", "dist", "release", "__pycache__"]

    if clean_cython:
        dirs_to_clean.append("build_cython")

    print("\n清理旧的构建文件...")
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            print(f"  删除目录: {dir_name}")
            try:
                shutil.rmtree(dir_name)
            except PermissionError:
                print(f"    ⚠️ 无法删除（目录被占用，跳过）")
            except Exception as e:
                print(f"    ⚠️ 删除失败: {e}")

    # 清理 .pyc 和编译产物
    patterns = ["*.pyc", "*.pyo"]
    if clean_cython:
        patterns.extend(["*.c", "*.pyd", "*.so", "*.html"])  # Cython 编译产物

    for root, dirs, files in os.walk("."):
        for file in files:
            if any(file.endswith(pattern.replace('*', '')) for pattern in patterns):
                file_path = os.path.join(root, file)
                if 'src' in file_path and clean_cython:  # 只清理 src 下的编译产物
                    print(f"  删除文件: {file_path}")
                    try:
                        os.remove(file_path)
                    except PermissionError:
                        print(f"    ⚠️ 无法删除（文件被占用）")

    print("✓ 清理完成\n")


def compile_cython(debug=False):
    """
    编译 Cython 代码

    Args:
        debug: 是否启用调试模式
    """
    print("=" * 70)
    print("第一步：Cython 编译")
    print("=" * 70)
    print()

    # 构建命令 (不使用 --inplace,避免路径重复问题)
    cmd = [
        sys.executable,
        "setup.py",
        "build_ext",  # 构建扩展
    ]

    if debug:
        cmd.append("--debug")  # 调试模式

    print(f"执行命令: {' '.join(cmd)}")
    print()

    try:
        result = subprocess.run(cmd, check=True)

        print("\n" + "=" * 70)
        print("✅ Cython 编译成功！")
        print("=" * 70)

        # 从 build 目录复制 .pyd/.so 文件到 src 目录
        build_lib = None
        for item in Path("build").iterdir():
            if item.is_dir() and item.name.startswith("lib."):
                build_lib = item
                break

        if build_lib and (build_lib / "src").exists():
            print("\n复制编译产物到 src 目录...")
            for pyd_file in build_lib.rglob("*.pyd"):
                rel_path = pyd_file.relative_to(build_lib)
                target = Path(rel_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(pyd_file, target)
                print(f"  复制: {pyd_file} -> {target}")

            for so_file in build_lib.rglob("*.so"):
                rel_path = so_file.relative_to(build_lib)
                target = Path(rel_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(so_file, target)
                print(f"  复制: {so_file} -> {target}")

        # 检查编译产物
        extensions = []
        extensions.extend(glob.glob("src/**/*.pyd", recursive=True))
        extensions.extend(glob.glob("src/**/*.so", recursive=True))

        if extensions:
            print(f"\n编译产物 ({len(extensions)} 个):")
            for ext in extensions:
                size_mb = Path(ext).stat().st_size / (1024 * 1024)
                print(f"  - {ext} ({size_mb:.2f} MB)")
        else:
            print("\n⚠️ 警告：未找到编译产物")

        # 查找 HTML 注释文件
        html_files = glob.glob("src/**/*.html", recursive=True)
        if html_files:
            print(f"\n注释文件 ({len(html_files)} 个):")
            print("  (可查看 Cython 优化情况)")
            for html in html_files[:3]:  # 只显示前3个
                print(f"  - {html}")

        return True

    except subprocess.CalledProcessError as e:
        print("\n✗ Cython 编译失败")
        print(f"错误: {e}")
        return False


def build_exe_with_pyinstaller(spec_file="windows-mcp.spec", clean=False):
    """
    使用 PyInstaller 打包

    Args:
        spec_file: spec 文件路径
        clean: 是否清理临时文件
    """
    print("\n" + "=" * 70)
    print("第二步：PyInstaller 打包")
    print("=" * 70)
    print()

    if not os.path.exists(spec_file):
        print(f"✗ 找不到 spec 文件: {spec_file}")
        return False

    cmd = ["pyinstaller"]

    if clean:
        cmd.append("--clean")

    cmd.extend(["--noconfirm", spec_file])

    print(f"执行命令: {' '.join(cmd)}")
    print()

    try:
        result = subprocess.run(cmd, check=True)

        print("\n" + "=" * 70)
        print("✅ PyInstaller 打包成功！")
        print("=" * 70)

        # 检查输出文件
        exe_path = Path("dist") / "windows-mcp.exe"
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"\n可执行文件: {exe_path}")
            print(f"文件大小: {size_mb:.2f} MB")

            # 复制到 release 目录
            release_dir = Path("release")
            release_dir.mkdir(exist_ok=True)
            release_exe = release_dir / "windows-mcp.exe"
            shutil.copy2(exe_path, release_exe)
            print(f"已复制到: {release_exe}")

        print("\n✨ 打包特性:")
        print("  ✅ 核心代码已编译成 C 扩展 (.pyd/.so)")
        print("  ✅ 难以被反编译工具还原源码")
        print("  ✅ 保持 Python 完整功能")
        print("  ✅ 单文件 exe，包含所有依赖")

        return True

    except subprocess.CalledProcessError as e:
        print("\n✗ PyInstaller 打包失败")
        print(f"错误: {e}")
        return False


def test_exe():
    """测试打包的 exe"""
    exe_path = Path("dist") / "windows-mcp.exe"

    if not exe_path.exists():
        print(f"✗ 找不到可执行文件: {exe_path}")
        return False

    print(f"\n测试可执行文件: {exe_path}")
    print("运行 --help 命令...\n")

    try:
        result = subprocess.run(
            [str(exe_path), "--help"],
            capture_output=True,
            text=True,
            timeout=10
        )

        print(result.stdout)

        if result.returncode == 0:
            print("✓ exe 运行正常")
            return True
        else:
            print("✗ exe 运行异常")
            print(result.stderr)
            return False

    except subprocess.TimeoutExpired:
        print("✗ exe 运行超时")
        return False
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Windows-MCP Cython 打包工具（防止反编译）"
    )
    parser.add_argument(
        "--skip-cython",
        action="store_true",
        help="跳过 Cython 编译（假设已编译）"
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="不清理旧的构建文件"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="启用调试模式"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="打包后测试 exe"
    )
    parser.add_argument(
        "--clean-cython",
        action="store_true",
        help="清理 Cython 编译产物"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制继续（跳过 C 编译器检查）"
    )

    args = parser.parse_args()

    print_banner()

    # 检查依赖
    if not check_cython():
        print("\n安装 Cython...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "cython"], check=True)
            print("✓ Cython 安装成功\n")
        except subprocess.CalledProcessError:
            return 1

    if not check_pyinstaller():
        print("\n安装 PyInstaller...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
            print("✓ PyInstaller 安装成功\n")
        except subprocess.CalledProcessError:
            return 1

    if not check_compiler():
        print("\n⚠️ 警告：没有 C 编译器，Cython 编译可能失败")
        if not args.force:
            try:
                response = input("是否继续? (y/n): ")
                if response.lower() != 'y':
                    return 1
            except EOFError:
                print("检测到非交互模式，使用 --force 参数强制继续")
                return 1
        else:
            print("使用 --force 参数，强制继续")

    # 清理旧文件
    if not args.no_clean:
        clean_build_dirs(clean_cython=args.clean_cython)

    # 第一步：Cython 编译
    if not args.skip_cython:
        if not compile_cython(debug=args.debug):
            return 1
    else:
        print("⏭️ 跳过 Cython 编译\n")

    # 第二步：PyInstaller 打包
    if not build_exe_with_pyinstaller(clean=not args.no_clean):
        return 1

    # 测试
    if args.test:
        test_exe()

    print("\n" + "=" * 70)
    print("🎉 打包流程完成！")
    print("=" * 70)
    print("\n提示:")
    print("  1. exe 文件位于 dist/ 和 release/ 目录")
    print("  2. 核心代码已编译成 C 扩展，难以反编译")
    print("  3. 可以安全分发给用户使用")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
