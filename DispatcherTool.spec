# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — 同时支持 macOS (.app) 与 Windows (.exe)。
# 用法：
#   pip install pyinstaller Pillow
#   pyinstaller DispatcherTool.spec --noconfirm --clean
# 默认产物：
#   macOS:   dist/DispatcherTool.app      (onedir 模式，启动快)
#   Windows: dist/DispatcherTool.exe      (onefile 单文件)

import sys
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

hiddenimports = []
hiddenimports += collect_submodules("PySide6")
hiddenimports += collect_submodules("shiboken6")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("resources", "resources"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "pydoc",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

EXE_KWARGS = dict(
    name="DispatcherTool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="resources/1.png",
)

if sys.platform == "darwin":
    # macOS：onedir 模式 + BUNDLE 生成 .app
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        **EXE_KWARGS,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="DispatcherTool",
    )
    app = BUNDLE(
        coll,
        name="DispatcherTool.app",
        icon="resources/1.png",
        bundle_identifier="com.dispatchertool.app",
        info_plist={
            "CFBundleName": "DispatcherTool",
            "CFBundleDisplayName": "调度员任务清单",
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "10.13",
        },
    )
else:
    # Windows：onefile 单文件 exe
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        **EXE_KWARGS,
    )
