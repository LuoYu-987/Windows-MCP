#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Cython 编译配置
将核心 Python 代码编译成 C 扩展，防止反编译
"""
import os
import sys
from pathlib import Path
from setuptools import setup, Extension
from Cython.Build import cythonize
import Cython.Compiler.Options

# 设置 Windows 控制台编码为 UTF-8
if sys.platform == 'win32':
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except Exception:
        pass

# 启用注释和行号追踪（便于调试）
Cython.Compiler.Options.annotate = True
Cython.Compiler.Options.emit_linenums = True

# 项目根目录
PROJECT_ROOT = Path(__file__).parent

def find_python_files(directory, exclude_patterns=None):
    """
    递归查找目录下的所有 .py 文件

    Args:
        directory: 搜索目录
        exclude_patterns: 排除的文件模式列表
    """
    if exclude_patterns is None:
        exclude_patterns = ['__init__.py', 'test_', 'setup']

    python_files = []
    for root, dirs, files in os.walk(directory):
        # 排除 __pycache__ 和测试目录
        dirs[:] = [d for d in dirs if d not in ['__pycache__', 'tests', 'test', '.pytest_cache']]

        for file in files:
            if file.endswith('.py'):
                # 检查是否应该排除
                should_exclude = any(pattern in file for pattern in exclude_patterns)
                if not should_exclude:
                    file_path = os.path.join(root, file)
                    python_files.append(file_path)

    return python_files


def create_extensions():
    """
    创建 Cython 扩展列表

    策略：
    - 编译 src/ 下的所有模块（除了 __init__.py）
    - 保留 main.py 为纯 Python（作为入口点）
    """
    extensions = []

    # 查找 src/ 下的所有 Python 文件
    src_dir = PROJECT_ROOT / "src"
    if src_dir.exists():
        python_files = find_python_files(str(src_dir))

        for py_file in python_files:
            # 将文件路径转换为模块名 (相对于 src 目录)
            rel_path = os.path.relpath(py_file, src_dir)
            module_name = rel_path.replace(os.sep, '.').replace('.py', '')
            full_module_name = f"src.{module_name}"

            print(f"  添加编译目标: {full_module_name} <- {py_file}")

            extensions.append(
                Extension(
                    name=full_module_name,
                    sources=[py_file],
                    # 编译选项
                    extra_compile_args=[
                        '/O2' if sys.platform == 'win32' else '-O3',  # 最大优化
                    ],
                )
            )

    return extensions


def main():
    """主编译流程"""
    print("=" * 60)
    print("Cython 编译配置")
    print("将 Python 代码编译成 C 扩展，防止反编译")
    print("=" * 60)
    print()

    # 创建扩展列表
    print("扫描需要编译的 Python 文件...")
    extensions = create_extensions()

    if not extensions:
        print("⚠️ 未找到需要编译的文件")
        return

    print(f"\n找到 {len(extensions)} 个模块需要编译\n")

    # Cython 编译选项
    compiler_directives = {
        'language_level': "3",  # Python 3 语法
        'embedsignature': True,  # 嵌入签名信息
        'boundscheck': False,  # 禁用边界检查（性能优化）
        'wraparound': False,  # 禁用负索引（性能优化）
        'cdivision': True,  # C 除法语义（性能优化）
        'initializedcheck': False,  # 禁用初始化检查（性能优化）
        'nonecheck': False,  # 禁用 None 检查（性能优化）
        'overflowcheck': False,  # 禁用溢出检查（性能优化）
        'always_allow_keywords': True,  # 允许关键字参数
    }

    # 执行编译
    setup(
        name="windows-mcp-cython",
        ext_modules=cythonize(
            extensions,
            compiler_directives=compiler_directives,
            build_dir="build_cython",  # 临时构建目录
            annotate=True,  # 生成 HTML 注释文件
            nthreads=4,  # 并行编译线程数
        ),
        zip_safe=False,
    )

    print("\n" + "=" * 60)
    print("✅ Cython 编译完成！")
    print("=" * 60)
    print("\n编译产物：")
    print("  - .pyd/.so 文件：编译后的扩展模块")
    print("  - .c 文件：中间 C 代码（可删除）")
    print("  - .html 文件：注释文件（可查看优化情况）")
    print()


if __name__ == "__main__":
    main()
