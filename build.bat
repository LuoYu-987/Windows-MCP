@echo off
REM Windows-MCP Cython 打包脚本
REM 使用 Cython 编译防止反编译

echo ========================================
echo Windows-MCP Cython 打包工具
echo 防止源码被反编译
echo ========================================
echo.

REM 检查 uv
uv --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 找不到 uv，请先安装 uv
    echo 安装命令: pip install uv
    pause
    exit /b 1
)

REM 运行打包脚本
uv run python build.py --force %*

if errorlevel 1 (
    echo.
    echo [错误] 打包失败
    pause
    exit /b 1
)

echo.
echo [成功] 打包完成！
echo.
echo 输出文件位于: dist\windows-mcp.exe
echo 核心代码已编译成 C 扩展，难以反编译
echo.

pause
