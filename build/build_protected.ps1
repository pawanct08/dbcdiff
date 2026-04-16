# build/build_protected.ps1 – Nuitka native-code protected build for dbcdiff-gui
#
# Usage  (from repo root):
#   .\build\build_protected.ps1
#
# Prerequisites:
#   pip install nuitka ordered-set zstandard pillow
#   A C/C++ compiler must be available (MSVC via Visual Studio, or MinGW-w64)
#
# Output:
#   dist\dbcdiff-gui.exe   (compiled native binary, harder to reverse-engineer)
#
# Notes:
#   • First run downloads Nuitka's C runtime (automatic, one-time ~10 MB).
#   • Compilation takes 3–10 minutes on first run; subsequent runs are faster.
#   • The resulting exe is NOT packaged with Python – it is truly native code.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Full path to Windows-Store Python (avoids WSL python on this machine) ──
$PYTHON     = "C:\Users\pcw1kor\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe"
$repoRoot   = Split-Path -Parent $PSScriptRoot
$buildDir   = Join-Path $repoRoot "build"
$distDir    = Join-Path $repoRoot "dist"
$iconPath   = Join-Path $buildDir "icon.ico"
$entryPoint = Join-Path $repoRoot "dbcdiff\__main__.py"

Push-Location $repoRoot

try {
    # ── Step 1: generate icon ────────────────────────────────────────────────
    Write-Host "→ Generating icon..." -ForegroundColor Cyan
    & $PYTHON "$buildDir\create_icon.py"

    # ── Step 2: run Nuitka ───────────────────────────────────────────────────
    Write-Host "→ Running Nuitka (this may take several minutes)..." -ForegroundColor Cyan

    $nuitkaArgs = @(
        "-m", "nuitka",
        "--onefile",                            # single .exe, self-extracting
        "--enable-plugin=pyside6",              # bundle PySide6 correctly
        "--windows-console-mode=disable",       # no console window
        "--windows-icon-from-ico=$iconPath",
        "--output-filename=dbcdiff.exe",
        "--output-dir=$distDir",
        # Include the dbcdiff package and shared data
        "--include-package=dbcdiff",
        "--include-package-data=dbcdiff",
        # Production optimisations
        "--python-flag=no_docstrings",
        "--python-flag=no_asserts",
        "--lto=yes",                            # link-time optimisation
        # Optional: obfuscation pass (comment out if it causes issues)
        # "--obfuscate-source",
        $entryPoint
    )

    & $PYTHON @nuitkaArgs

    # ── Step 3: report ───────────────────────────────────────────────────────
    $exe = Join-Path $distDir "dbcdiff.exe"
    if (Test-Path $exe) {
        $size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
        Write-Host ""
        Write-Host "✔  Protected build complete: $exe  (${size} MB)" -ForegroundColor Green
    } else {
        Write-Error "Build finished but exe not found at $exe"
    }
} finally {
    Pop-Location
}
