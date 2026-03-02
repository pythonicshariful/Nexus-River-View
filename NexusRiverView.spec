# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['run_gui.py'],
    pathex=[],
    binaries=[],
    datas=[('templates', 'templates'), ('static', 'static'), ('admin_config.json', '.'), ('.env', '.'), ('credentials.json', '.'), ('nexus-river-view-600x866.ico', '.'), ('C:\\Users\\USER\\AppData\\Roaming\\Python\\Python313\\site-packages\\certifi\\cacert.pem', 'certifi')],
    hiddenimports=['engineio.async_drivers.threading', 'certifi', 'pandas', 'openpyxl', 'openpyxl.cell._writer', 'webview', 'tkinter', 'filedialog'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='NexusRiverView',
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
    icon=['nexus-river-view-600x866.ico'],
)
