# DocForge 打包指南

本指南将帮助你将 Python 源码打包为 Windows 可执行文件 (.exe)。

## 1. 环境准备

确保已安装以下工具：
- Python 3.10+
- PyInstaller

```bash
.\.venv\Scripts\python -m pip install pyinstaller
.\.venv\Scripts\python -m pip install -r requirements.txt
```

## 2. 执行打包

在项目根目录下，运行以下命令：

```bash
.\.venv\Scripts\pyinstaller --clean --noconfirm build.spec
```

打包完成后，可执行文件将位于 `dist/DocForge/DocForge.exe`。

如果需要不依赖 spec 的备用打包命令（包含 exe 图标）：

```bash
.\.venv\Scripts\pyinstaller --noconfirm --clean --windowed --name DocForge --icon assets/icons/app_icon.ico --add-data "assets;assets" --add-data "templates;templates" --add-data "themes;themes" main.py
```

## 3. 外部依赖说明

本程序依赖以下外部工具，打包后的程序在分发时需要注意：

### Pandoc
- 程序运行时需要 Pandoc。
- 建议将 `pandoc.exe` 放置在生成的 `dist/DocForge/` 目录中，或者确保用户电脑已安装 Pandoc 并配置了环境变量。
- 下载地址: https://pandoc.org/installing.html

### Typst (PDF 引擎)
- 程序导出 PDF 需要 Typst。
- 项目中包含了一个 `typst-x86_64-pc-windows-msvc` 文件夹。
- **推荐做法**: 将该文件夹下的 `typst.exe` 复制到 `dist/DocForge/` 目录中，程序会自动查找当前目录下的 `typst.exe` (如果代码支持) 或配置环境变量。
- 如果代码中是通过 `shutil.which` 查找，确保 `typst.exe` 在系统 PATH 中，或者与主程序同级。

## 4. 常见问题

- **缺少模块**: 如果运行 exe 报错 `ModuleNotFoundError`，请检查 `build.spec` 中的 `hiddenimports`。
- **资源缺失**: 如果图标或模板加载失败，请检查 `dist/DocForge/assets` 和 `dist/DocForge/templates` 目录是否存在。
- **打包报错**: 如果报错 `ValueError: Received icon image ... is not in the correct format`，请确保使用的是 `.ico` 格式的图标。本项目构建脚本已配置为使用 `assets/icons/app_icon.ico`。
- **重复打包失败**: 如果报错 `PermissionError` 或提示文件被占用，请先关闭正在运行的 `DocForge.exe` 后再执行打包。

## 5. 清理

打包前建议运行清理脚本（已执行）以移除临时文件。
打包后会生成 `build/` 和 `dist/` 目录，可以随时删除重新构建。
