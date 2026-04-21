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

    $pyiArgs = @(
        "--onefile",
        # Note: NOT --windowed so the CLI path can write to the console.
        # The GUI path hides the console window at runtime via win32 API.
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
