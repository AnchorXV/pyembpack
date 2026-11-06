$ErrorActionPreference = "Stop"

$dist = "dist"
$entry = "pyembpack\__main__.py"

if (-not (Test-Path $dist)) {
    New-Item -ItemType Directory -Path $dist | Out-Null
}

$ver = (Select-String -Path "pyembpack\__init__.py" -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
$ver4 = if ($ver -match '^(\d+)\.(\d+)\.(\d+)') {
    "$($matches[1]).$($matches[2]).$($matches[3]).0"
} else {
    "0.0.0.0"
}

Write-Host "Building pyembpack v$ver ..." -ForegroundColor Cyan

python -m pip install -U nuitka ordered-set zstandard tqdm

python -m nuitka `
    --onefile `
    --assume-yes-for-downloads `
    --windows-console-mode=force `
    --include-package=pyembpack `
    --include-package=tqdm `
    --company-name="pyembpack" `
    --product-name="pyembpack" `
    --product-version=$ver `
    --file-version=$ver4 `
    --output-filename=pyembpack.exe `
    --output-dir=$dist `
    $entry

if ($LASTEXITCODE -ne 0) {
    Write-Host "Build FAILED (exit code $LASTEXITCODE)" -ForegroundColor Red
    exit 1
}

$exe = Join-Path $dist "pyembpack.exe"
$size = [math]::Round((Get-Item $exe).Length / 1MB, 1)

Write-Host ""
Write-Host "Build complete: $exe ($size MB)" -ForegroundColor Green