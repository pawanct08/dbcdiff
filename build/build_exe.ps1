# build/build_exe.ps1 - PyInstaller one-file windowed build for dbcdiff
#
# Usage  (from repo root):
#   .\build\build_exe.ps1
#
# Prerequisite:
#   pip install pyinstaller pillow
#
# Output:
#   dist\dbcdiff.exe   (single standalone executable, ~50-90 MB)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Resolve Python: prefer a native Windows install, then 'py', then 'python'
$windowsPython = Join-Path $env:LocalAppData "Programs\Python\Python313\python.exe"
$PYTHON = if (Test-Path $windowsPython) {
    $windowsPython
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    "py"
} else {
    "python"
}
$repoRoot  = Split-Path -Parent $PSScriptRoot
$buildDir  = Join-Path $repoRoot "build"
$distDir   = Join-Path $repoRoot "dist"
$iconPath  = Join-Path $buildDir "icon.ico"
$entryPoint = Join-Path $repoRoot "dbcdiff\__main__.py"

Push-Location $repoRoot

try {
    # Step 1: generate icon
    Write-Host "Generating icon..." -ForegroundColor Cyan
    & $PYTHON "$buildDir\create_icon.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Icon generation failed with exit code $LASTEXITCODE"
    }

    # Step 2: run PyInstaller
    Write-Host "Running PyInstaller..." -ForegroundColor Cyan

    # ---------------------------------------------------------------------------
    # Modules to exclude from the bundle.
    # Removing unused Qt/PySide6 sub-modules is the single biggest lever
    # for reducing exe size (QtWebEngine alone is ~150-200 MB).
    # ---------------------------------------------------------------------------
    $excludeMods = @(
        # ── Unused PySide6 / Qt modules ──────────────────────────────────────
        "PySide6.Qt3DAnimation",  "PySide6.Qt3DCore",    "PySide6.Qt3DExtras",
        "PySide6.Qt3DInput",      "PySide6.Qt3DLogic",   "PySide6.Qt3DRender",
        "PySide6.QtAxContainer",  "PySide6.QtBluetooth", "PySide6.QtCanvasPainter",
        "PySide6.QtCharts",       "PySide6.QtConcurrent","PySide6.QtDataVisualization",
        "PySide6.QtDBus",         "PySide6.QtDesigner",
        "PySide6.QtGraphs",       "PySide6.QtGraphsWidgets",
        "PySide6.QtHelp",         "PySide6.QtHttpServer",
        "PySide6.QtLocation",     "PySide6.QtMultimedia","PySide6.QtMultimediaWidgets",
        "PySide6.QtNetworkAuth",  "PySide6.QtNfc",       "PySide6.QtOpenGLWidgets",
        "PySide6.QtPdf",          "PySide6.QtPdfWidgets",
        "PySide6.QtPositioning",  "PySide6.QtQml",
        "PySide6.QtQuick",        "PySide6.QtQuick3D",
        "PySide6.QtQuickControls2","PySide6.QtQuickTest","PySide6.QtQuickWidgets",
        "PySide6.QtRemoteObjects",
        "PySide6.QtScxml",        "PySide6.QtSensors",
        "PySide6.QtSerialBus",    "PySide6.QtSerialPort",
        "PySide6.QtSpatialAudio", "PySide6.QtSql",       "PySide6.QtStateMachine",
        "PySide6.QtTest",         "PySide6.QtTextToSpeech",
        "PySide6.QtUiTools",
        # QtWebEngine is ~150-200 MB; the 3-D sim panel falls back gracefully
        # to an embedded fallback message when these modules are absent.
        "PySide6.QtWebChannel",
        "PySide6.QtWebEngineCore","PySide6.QtWebEngineQuick","PySide6.QtWebEngineWidgets",
        "PySide6.QtWebSockets",   "PySide6.QtWebView",
        # ── Heavy scientific / dev-only Python packages ───────────────────────
        "numpy", "pandas", "matplotlib", "scipy",
        "PIL", "Pillow", "IPython", "jupyter",
        "tkinter", "turtle",
        "setuptools", "distutils",
        "unittest", "pytest", "doctest",
        "pdb", "profile", "cProfile", "pstats", "timeit", "trace"
    )
    $excludeArgs = $excludeMods | ForEach-Object { "--exclude-module=$_" }

    # Note: --add-data=dbcdiff:dbcdiff removed — the package contains no
    # static asset files (3d_sim.html is embedded as a string in gui.py).
    # resources/style.qss IS needed at runtime for the themed GUI.
    # Tip: install UPX (https://upx.github.io) for an extra ~30 % compression.
    $pyiArgs = @(
        "--onefile",
        # Note: NOT --windowed so the CLI path can write to the console.
        # The GUI path hides the console window at runtime via win32 API.
        "--icon=$iconPath",
        "--name=dbcdiff",
        "--distpath=$distDir",
        "--workpath=$buildDir\_pyinstaller_work",
        "--specpath=$buildDir",
        "--optimize=2",
        "--add-data=$repoRoot\resources$([IO.Path]::PathSeparator)resources",
        $entryPoint
    )

    & $PYTHON -m PyInstaller @pyiArgs @excludeArgs
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }

    # Step 3: report
    $exe = Join-Path $distDir "dbcdiff.exe"
    if (Test-Path $exe) {
        $size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
        Write-Host ""
        Write-Host "Build complete: $exe (${size} MB)" -ForegroundColor Green
    } else {
        Write-Error "Build finished but exe not found at $exe"
    }
} finally {
    Pop-Location
}
