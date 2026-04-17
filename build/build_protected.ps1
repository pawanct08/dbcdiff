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
$PYTHON     = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
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
        "--lto=no",                             # disable LTO; Zig 0.14.0 LTO exhausts RAM on large PySide6 builds
        "--assume-yes-for-downloads",           # auto-accept all Nuitka download prompts
        # Optional: obfuscation pass (comment out if it causes issues)
        # "--obfuscate-source",
        $entryPoint
    )

    # ── LIB path fixup for Windows Store Python ─────────────────────────────
    # Windows Store Python installs python313.lib to an ACL-protected
    # WindowsApps directory.  Copy it once to C:\Temp\py313libs\ and tell
    # the Zig linker (used by Nuitka when MSVC is too old) where to find it.
    $libDir = "C:\Temp\py313libs"
    if (-not (Test-Path "$libDir\python313.lib")) {
        Write-Host "  → Copying python313.lib to $libDir ..." -ForegroundColor Yellow
        $null = New-Item -ItemType Directory -Force -Path $libDir
        $src  = (& $PYTHON -c "import sys,os; print(os.path.join(sys.prefix,'libs','python313.lib'))")
        [System.IO.File]::Copy($src, "$libDir\python313.lib", $true)
    }
    $env:LIB = "$libDir;$env:LIB"

    # Nuitka writes informational messages to stderr; temporarily allow that
    # without aborting the script (ErrorActionPreference=Stop kills on any stderr).
    $ErrorActionPreference = "Continue"
    & $PYTHON @nuitkaArgs
    $nuitkaExit = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($nuitkaExit -ne 0) { throw "Nuitka exited with code $nuitkaExit" }

    # ── Step 3: report ───────────────────────────────────────────────────────
    $exe = Join-Path $distDir "dbcdiff.exe"
    if (Test-Path $exe) {
        $size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
        Write-Host ""
        Write-Host "[OK] Protected build complete: $exe  (${size} MB)" -ForegroundColor Green
    } else {
        Write-Error "Build finished but exe not found at $exe"
    }
} finally {
    Pop-Location
}
