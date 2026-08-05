@echo off
REM 在 Windows 上打包 DispatcherTool.exe（单文件）
setlocal
cd /d "%~dp0"

echo ==> 安装依赖
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller Pillow

echo ==> 清理旧产物
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo ==> 开始打包
python -m PyInstaller DispatcherTool.spec --noconfirm --clean

if exist dist\DispatcherTool.exe (
    echo ✅ 打包成功：dist\DispatcherTool.exe
    echo    双击运行即可。
) else (
    echo ❌ 打包失败
    exit /b 1
)
endlocal
