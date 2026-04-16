# build/build_exe.ps1 – PyInstaller one-file windowed build for dbcdiff-gui
#
# Usage  (from repo root):
#   .\build\build_exe.ps1
#
# Prerequisite:
#   pip install pyinstaller pillow
#
# Output:
#   dist\dbcdiff-gui.exe   (single standalone executable, ~50-90 MB)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Full path to Windows-Store Python (avoids WSL python on this machine) ──
$PYTHON     = "C:\Users\pcw1kor\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe"
$repoRoot  = Split-Path -Parent $PSScriptRoot
$buildDir  = Join-Path $repoRoot "build"
$distDir   = Join-Path $repoRoot "dist"
$iconPath  = Join-Path $buildDir "icon.ico"
$entryPoint = Join-Path $repoRoot "dbcdiff\__main__.py"

Push-Location $repoRoot

try {
    # ── Step 1: generate icon ────────────────────────────────────────────────
    Write-Host "→ Generating icon..." -ForegroundColor Cyan
    & $PYTHON "$buildDir\create_icon.py"

    # ── Step 2: run PyInstaller ──────────────────────────────────────────────
    Write-Host "→ Running PyInstaller..." -ForegroundColor Cyan

    $pyiArgs = @(
        "--onefile",
        "--windowed",                          # no console window
        "--icon=$iconPath",
        "--name=dbcdiff",
        "--distpath=$distDir",
        "--workpath=$buildDir\_pyinstaller_work",
        "--specpath=$buildDir",
        # Bundle the entire package directory
        "--add-data=dbcdiff$([IO.Path]::PathSeparator)dbcdiff",
        $entryPoint
    )

    & $PYTHON -m PyInstaller @pyiArgs

    # ── Step 3: report ───────────────────────────────────────────────────────
    $exe = Join-Path $distDir "dbcdiff.exe"
    if (Test-Path $exe) {
        $size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
        Write-Host ""
        Write-Host "✔  Build complete: $exe  (${size} MB)" -ForegroundColor Green
    } else {
        Write-Error "Build finished but exe not found at $exe"
    }
} finally {
    Pop-Location
}
