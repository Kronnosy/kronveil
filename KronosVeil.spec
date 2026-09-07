# -*- mode: python ; coding: utf-8 -*-
# PyInstaller specification for Kronos Veil (KV)

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),
    ],
    hiddenimports=[
        'kronos_veil',
        'kronos_veil.app',
        'kronos_veil.config',
        'kronos_veil.overlay',
        'kronos_veil.settings_window',
        'kronos_veil.tray',
        'kronos_veil.hotkeys',
        'kronos_veil.windows.capture_protection',
        'kronos_veil.windows.window_styles',
        'kronos_veil.chat.base',
        'kronos_veil.chat.demo',
        'kronos_veil.chat.twitch',
        'kronos_veil.chat.youtube',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='KronosVeil',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.png',
)
