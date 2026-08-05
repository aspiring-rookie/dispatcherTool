# 打包说明

本项目使用 [PyInstaller](https://pyinstaller.org/) 把 Python + PySide6 应用打包成原生可执行文件，**目标平台**：

- **macOS** → `dist/DispatcherTool.app`（onedir 模式 bundle，可在 macOS 双击运行）
- **Windows** → `dist/DispatcherTool.exe`（onefile 单文件，无需安装）

> ⚠️ PyInstaller 不能交叉编译：要在 macOS 出 `.app`、在 Windows 出 `.exe`，需要在对应系统上分别运行打包脚本。

---

## 一、环境准备

两个平台都先确认：

```bash
python --version    # 建议 3.9 或更高
```

`requirements.txt` 已经包含 `PySide6`，打包脚本会再自动安装 `pyinstaller`。

---

## 二、macOS 打包

在 macOS 终端中：

```bash
cd DispatcherTool
bash build_macos.sh
```

打包完成后：

- 产物：`dist/DispatcherTool.app`
- 双击运行；或命令行：`open dist/DispatcherTool.app`
- 数据库位置：`~/Library/Application Support/DispatcherTool/dispatcher.db`
- 退出时自动备份到：`~/Library/Application Support/DispatcherTool/backup/`

**首次启动可能被 Gatekeeper 拦截**（未签名），前往 *系统设置 → 隐私与安全性*，点"仍要打开"放行即可。要彻底消除提示，需要做 Apple Developer 签名（不在本脚本范围内）。

---

## 三、Windows 打包

在 Windows PowerShell 或 CMD 中：

```bat
cd DispatcherTool
build_windows.bat
```

打包完成后：

- 产物：`dist\DispatcherTool.exe`
- 双击运行；首次启动可能弹窗"Windows 已保护你的电脑"（未签名），点"更多信息 → 仍要运行"
- 数据库位置：`%APPDATA%\DispatcherTool\dispatcher.db`
- 退出时自动备份到：`%APPDATA%\DispatcherTool\backup\`

**Windows Defender 误报**：PyInstaller 打的包经常被杀软误判，提交给 [Microsoft 安全情报](https://www.microsoft.com/wdsi/filesubmission) 申诉即可，或自行做代码签名。

---

## 四、原理说明（你问"是怎么完成的"）

1. **`DispatcherTool.spec`** 是 PyInstaller 的项目配置文件，定义：
   - 入口脚本 `main.py`
   - 资源：把 `resources/` 目录打包进可执行文件（运行时通过 `sys._MEIPASS` 解出）
   - 隐藏导入：用 `collect_submodules("PySide6")` 把 PySide6 所有 Qt 插件都带上，避免运行时缺模块
   - 关闭控制台（`console=False`）
   - **macOS 分支**：用 `EXE + COLLECT` 生成 onedir 目录，再调 `BUNDLE` 包成 `.app`，注入 `Info.plist`（应用名、版本、高 DPI 支持）
   - **Windows 分支**：直接用 `EXE` 把所有依赖塞进单个 `.exe`（PE 文件）

2. **资源路径处理**：`main.py` 里的 `resource_path()` 函数会先看 `sys._MEIPASS`（PyInstaller 运行时解压目录），找不到再退回源码目录，所以 **同一份代码既能开发模式跑，也能在打包后跑**。

3. **图标嵌入**：spec 中 `icon="resources/1.png"` 把图标嵌进可执行文件：
   - **Windows**：建议 `.ico`；新版 PyInstaller 也接受 `.png`，若启动后任务栏图标为默认值，把 `1.png` 转成 `1.ico` 放回 `resources/` 即可
   - **macOS**：需要 `.icns`；脚本会自动安装 Pillow，PyInstaller 调用 Pillow 把 `1.png` 转成 `icon.icns` 嵌入

4. **macOS 签名**：默认 ad-hoc 签名（未付费开发者证书也能本地运行），脚本里执行 `xattr -cr` 清除扩展属性 + `codesign -s -` 自签。Gatekeeper 首次仍会拦，"系统设置 → 隐私与安全性 → 仍要打开"放行即可。要彻底消除提示需要 Apple Developer 签名（不在本脚本范围）。

5. **`--noconfirm --clean`**：清掉旧缓存再打，避免改了代码没生效。

6. **打包体积**：PySide6 全功能打包后约 80–550MB（含 Qt 全套，体积随平台和模式差异较大）。要进一步瘦身可在 spec 的 `excludes` 加上 `["PySide6.Qt3D", "PySide6.QtWebEngine", "PySide6.QtCharts", ...]` 等不需要的模块。

---

## 五、产物目录速查

```
DispatcherTool/
├── build/                 # 中间产物（可删）
├── dist/                  # ← 最终产物
│   ├── DispatcherTool.app      # macOS
│   └── DispatcherTool.exe      # Windows
├── resources/             # 图标，已被打进产物，分发时不需要单独携带
├── DispatcherTool.spec    # PyInstaller 配置
├── build_macos.sh
├── build_windows.bat
└── ...源码
```

打包成功后，直接把 `dist/DispatcherTool.app`（或 `.exe`）拷给使用者即可，无需安装 Python 环境。
