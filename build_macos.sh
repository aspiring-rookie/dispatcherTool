#!/usr/bin/env bash
# 在 macOS 上打包 DispatcherTool.app
set -euo pipefail

cd "$(dirname "$0")"

echo "==> 安装依赖"
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 -m pip install pyinstaller Pillow

echo "==> 清理旧产物"
rm -rf build dist
# 清理资源里的 .DS_Store 等 macOS 扩展属性，避免 codesign 抱怨
find resources -name ".DS_Store" -delete 2>/dev/null || true
xattr -rc resources 2>/dev/null || true

echo "==> 开始打包"
python3 -m PyInstaller DispatcherTool.spec --noconfirm --clean

APP="dist/DispatcherTool.app"
if [ -d "$APP" ]; then
    # 清除扩展属性后再签名，避免 PyInstaller 自动签名时报 "resource fork" 错
    xattr -cr "$APP"
    if codesign -s - --force --all-architectures --timestamp --deep "$APP" 2>/dev/null; then
        echo "✅ 已完成 ad-hoc 签名"
    else
        echo "⚠️ 签名失败，可手动执行：xattr -cr \"$APP\" && codesign -s - --force --deep \"$APP\""
    fi
    SIZE=$(du -sh "$APP" | awk '{print $1}')
    echo "✅ 打包成功：$APP  (${SIZE})"
    echo "   双击运行，或命令行：open $APP"
else
    echo "❌ 打包失败，未生成 $APP"
    exit 1
fi
