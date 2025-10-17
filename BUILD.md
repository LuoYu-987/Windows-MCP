# Windows-MCP 打包指南

本文档说明如何将 Windows-MCP 打包成可执行文件(exe)。

## 🔒 打包方式

本项目使用 **Cython + PyInstaller** 打包，防止源码被反编译:

```
.py → Cython → .c → C 编译器 → .pyd → PyInstaller → .exe
```

**特点:**
- ✅ **防止源码泄露** - 核心代码编译成 C 扩展
- ✅ **性能提升** - C 代码运行更快
- ✅ **难以反编译** - 需要专业逆向工程技能
- ✅ **单文件 exe** - 包含所有依赖

## 📋 前置要求

### 1. Python 3.13+
```bash
python --version
```

### 2. 安装 C 编译器 (Windows 必需)

下载安装 [Visual Studio Build Tools](https://visualstudio.microsoft.com/downloads/)

1. 运行安装程序
2. 选择 **"Desktop development with C++"**
3. 安装完成后重启命令行

**验证安装:**
```bash
cl.exe
```

### 3. 安装 Python 依赖
```bash
# 安装项目依赖和构建工具
uv sync --extra build
```

## 🚀 一键打包 (推荐)

```bash
# 完整打包流程
uv run python build.py --force
```

这个命令会:
1. ✅ 检查依赖 (Cython、PyInstaller、C编译器)
2. ✅ 使用 Cython 编译核心代码
3. ✅ 使用 PyInstaller 打包成 exe
4. ✅ 输出到 `dist/` 和 `release/` 目录

**首次打包约需 5 分钟**

## 📦 输出文件

打包完成后:
- `dist/windows-mcp.exe` - 主输出文件 (~62 MB)
- `release/windows-mcp.exe` - 发布版本 (自动复制)

## 🔧 高级选项

```bash
# 显示帮助
uv run python build.py --help

# 跳过 Cython 编译 (假设已编译)
uv run python build.py --force --skip-cython

# 不清理旧文件
uv run python build.py --force --no-clean

# 清理 Cython 编译产物
uv run python build.py --force --clean-cython

# 打包后测试 exe
uv run python build.py --force --test
```

## 📂 项目结构

### 编译前
```
Windows-MCP/
├── main.py                 # 入口文件 (保持 .py)
├── src/
│   ├── desktop/
│   │   ├── service.py     # 将被编译
│   │   └── views.py       # 将被编译
│   └── tree/
│       ├── service.py     # 将被编译
│       └── views.py       # 将被编译
├── setup.py               # Cython 编译配置
├── windows-mcp.spec       # PyInstaller 配置
└── build.py               # 一键打包脚本
```

### 编译后
```
Windows-MCP/
├── main.py                 # 入口文件 (仍为 .py)
├── src/
│   ├── desktop/
│   │   ├── service.pyd    # ✅ 编译后的 C 扩展
│   │   ├── service.c      # 中间 C 代码 (可删除)
│   │   └── service.html   # 优化报告 (可删除)
│   └── ...
├── build/                  # 临时构建目录 (可删除)
├── dist/
│   └── windows-mcp.exe    # 最终可执行文件 ✅
└── release/
    └── windows-mcp.exe    # 发布版本 ✅
```

## 🧪 测试 exe

```bash
# 查看帮助
dist\windows-mcp.exe --help

# 查看版本
dist\windows-mcp.exe --version

# 运行服务器 (stdio 模式)
dist\windows-mcp.exe --transport stdio
```

## 🐛 常见问题

### Q: 找不到 C 编译器
**错误信息:**
```
error: Microsoft Visual C++ 14.0 or greater is required
```

**解决方案:**
1. 安装 Visual Studio Build Tools (见上方链接)
2. 重启命令行
3. 验证: 运行 `cl.exe`

### Q: 打包失败
**解决方案:**
1. 确保已运行 `uv sync --extra build`
2. 检查 C 编译器是否正确安装
3. 使用 `--force` 参数跳过编译器检查

### Q: exe 文件太大
**正常情况:**
- exe 大小约 60-70 MB
- 包含了 Python 运行时和所有依赖
- 这是单文件打包的正常大小

### Q: 修改代码后如何重新打包
**解决方案:**
```bash
# 清理并重新打包
uv run python build.py --force --clean-cython
```

### Q: 如何查看 Cython 优化情况
**解决方案:**
编译后会生成 `.html` 文件，用浏览器打开查看:
```
src/desktop/service.html
```

**颜色说明:**
- 🟢 **白色/浅黄色** = 已优化为 C 代码
- 🟡 **深黄色** = 部分优化
- 🔴 **红色** = 未优化 (仍为 Python 调用)

## 🔒 安全性

### 反编译难度对比

| 文件类型 | 反编译工具 | 难度 | 源码恢复率 |
|---------|-----------|------|-----------|
| **.pyc** (标准) | uncompyle6 | 🟢 简单 | ~90% |
| **.pyd** (Cython) | IDA Pro | 🔴 困难 | ~10% |

**Cython 打包后:**
- ✅ 源码已转换为 C 代码并编译成机器码
- ✅ 变量名和逻辑结构被混淆
- ✅ 需要专业逆向工程技能才能部分恢复
- ✅ 适合分发给客户使用

## 🔄 开发工作流

```bash
# 日常开发 - 直接运行 Python
uv run python main.py

# 测试功能
uv run python main.py --help

# 发布前 - 打包成 exe
uv run python build.py --force

# 测试打包结果
dist\windows-mcp.exe --help
```

## 📊 编译产物详情

成功编译后会生成 8 个 C 扩展模块 (~0.7 MB):

- src.desktop.config (0.02 MB)
- src.desktop.launch_cn_plus (0.20 MB)
- src.desktop.service (0.15 MB)
- src.desktop.views (0.05 MB)
- src.tree.config (0.02 MB)
- src.tree.service (0.15 MB)
- src.tree.utils (0.04 MB)
- src.tree.views (0.07 MB)

## ⚠️ 重要提示

1. **首次打包时间** - 约需 5 分钟 (包含 Cython 编译和 C 编译)
2. **必须安装 C 编译器** - Windows 需要 Visual Studio Build Tools
3. **打包后的 exe 难以被反编译** - 适合发布给客户
4. **修改代码后需要重新编译** - 使用 `--clean-cython` 参数

## 📖 相关文件

- `setup.py` - Cython 编译配置
- `windows-mcp.spec` - PyInstaller 打包配置
- `build.py` - 一键打包脚本
- `build.bat` - Windows 快捷打包脚本

## 📚 参考资料

- [Cython 官方文档](https://cython.readthedocs.io/)
- [PyInstaller 文档](https://pyinstaller.org/)
- [Visual Studio Build Tools](https://visualstudio.microsoft.com/downloads/)

---

**总结:** 使用 `uv run python build.py --force` 一键打包，生成的 exe 文件可安全分发，源码难以被反编译。
