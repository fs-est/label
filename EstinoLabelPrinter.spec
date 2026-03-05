# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['label_gui.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'usb',
        'usb.core',
        'usb.backend.libusb1',
        'usb.backend.libusb0',
        'brother_ql',
        'brother_ql.raster',
        'brother_ql.conversion',
        'brother_ql.backends',
        'brother_ql.backends.helpers',
        'brother_ql.backends.pyusb',
        'brother_ql.models',
        'brother_ql.labels',
    ],
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
    name='EstinoLabelPrinter',
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
)
