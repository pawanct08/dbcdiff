# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['dbcdiff\\__main__.py'],
    pathex=[],
    binaries=[],
    datas=[('dbcdiff', 'dbcdiff')],
    # dbcdiff submodules are imported conditionally in __main__.py, so
    # PyInstaller's static analyser misses them — list them explicitly.
    hiddenimports=[
        'dbcdiff.cli',
        'dbcdiff.gui',
        'dbcdiff.engine',
        'dbcdiff.baseline',
        'dbcdiff.converter',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtSvg',
        'PySide6.QtXml',
        'openpyxl',
        'openpyxl.styles',
        'openpyxl.utils',
        'openpyxl.utils.dataframe',
        'openpyxl.writer.excel',
        'openpyxl.reader.excel',
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
    name='dbcdiff',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # console=True so CLI output is visible in a terminal AND crash errors
    # are shown.  The GUI still launches fine; only difference is a brief
    # console window appears when double-clicking to open the GUI.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
