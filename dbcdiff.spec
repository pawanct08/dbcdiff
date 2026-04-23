# -*- mode: python ; coding: utf-8 -*-


# ---------------------------------------------------------------------------
# Modules excluded from the bundle.
# Removing unused PySide6/Qt sub-modules is the single biggest size lever;
# QtWebEngineCore/Widgets alone accounts for ~150-200 MB.
# The 3-D simulation panel falls back gracefully when WebEngine is absent.
# ---------------------------------------------------------------------------
_EXCLUDES = [
    # Unused PySide6 / Qt modules
    'PySide6.Qt3DAnimation',  'PySide6.Qt3DCore',    'PySide6.Qt3DExtras',
    'PySide6.Qt3DInput',      'PySide6.Qt3DLogic',   'PySide6.Qt3DRender',
    'PySide6.QtAxContainer',  'PySide6.QtBluetooth', 'PySide6.QtCanvasPainter',
    'PySide6.QtCharts',       'PySide6.QtConcurrent','PySide6.QtDataVisualization',
    'PySide6.QtDBus',         'PySide6.QtDesigner',
    'PySide6.QtGraphs',       'PySide6.QtGraphsWidgets',
    'PySide6.QtHelp',         'PySide6.QtHttpServer',
    'PySide6.QtLocation',     'PySide6.QtMultimedia','PySide6.QtMultimediaWidgets',
    'PySide6.QtNetworkAuth',  'PySide6.QtNfc',       'PySide6.QtOpenGLWidgets',
    'PySide6.QtPdf',          'PySide6.QtPdfWidgets',
    'PySide6.QtPositioning',  'PySide6.QtQml',
    'PySide6.QtQuick',        'PySide6.QtQuick3D',
    'PySide6.QtQuickControls2','PySide6.QtQuickTest','PySide6.QtQuickWidgets',
    'PySide6.QtRemoteObjects',
    'PySide6.QtScxml',        'PySide6.QtSensors',
    'PySide6.QtSerialBus',    'PySide6.QtSerialPort',
    'PySide6.QtSpatialAudio', 'PySide6.QtSql',       'PySide6.QtStateMachine',
    'PySide6.QtTest',         'PySide6.QtTextToSpeech',
    'PySide6.QtUiTools',
    'PySide6.QtWebChannel',
    'PySide6.QtWebEngineCore','PySide6.QtWebEngineQuick','PySide6.QtWebEngineWidgets',
    'PySide6.QtWebSockets',   'PySide6.QtWebView',
    # Heavy scientific / dev-only packages
    'numpy', 'pandas', 'matplotlib', 'scipy',
    'PIL', 'Pillow', 'IPython', 'jupyter',
    'tkinter', 'turtle',
    'setuptools', 'distutils',
    'unittest', 'pytest', 'doctest',
    'pdb', 'profile', 'cProfile', 'pstats', 'timeit', 'trace',
]

a = Analysis(
    ['dbcdiff\\__main__.py'],
    pathex=[],
    binaries=[],
    # dbcdiff package has no static asset files (3d_sim.html is embedded as a
    # string literal in gui.py).  Only bundle the QSS theme file.
    datas=[('resources', 'resources')],
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
    excludes=_EXCLUDES,
    noarchive=False,
    optimize=2,   # strip docstrings from bytecode (level 0/1/2)
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
    strip=False,   # keep False on Windows — strip can break DLLs
    upx=True,       # no-op if UPX not installed; install from https://upx.github.io
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
