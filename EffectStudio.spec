# -*- mode: python ; coding: utf-8 -*-
# EffectStudio 打包配置：pyinstaller EffectStudio.spec
# 产物 dist/EffectStudio/EffectStudio.exe（onedir，pywebview 原生窗口）。
# web/ vendor/ config.json 作为只读资源打进 _internal，
# output/ tmp/ logs/ 与 config.local.json 由程序在 exe 旁边自建/读取。

import os
from PyInstaller.utils.hooks import collect_all

block_cipher = None

datas = [
    ('web', 'web'),
    ('vendor', 'vendor'),
    ('config.json', '.'),
    ('assets/icon.ico', 'assets'),
]
binaries = []
hiddenimports = []

# pywebview 的 Windows 后端（winforms + WebView2）与 .NET 桥运行时
for pkg in ('webview', 'clr_loader', 'pythonnet'):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
hiddenimports += ['webview.platforms.winforms', 'webview.platforms.edgechromium']

a = Analysis(
    ['app.py'],
    pathex=[os.path.abspath('.')],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'pytest', 'setuptools'],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='EffectStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # 无黑窗口；日志去 logs/app.log 看
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='EffectStudio',
)
