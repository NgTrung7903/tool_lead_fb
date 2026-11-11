$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$releasePath = Join-Path $PSScriptRoot 'dist\revoland-link-v18'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Cài môi trường bằng install.ps1 trước.' }
& $pythonPath -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Không cài được thư viện build.' }
$browserExe = & $pythonPath -c 'from playwright.sync_api import sync_playwright; p=sync_playwright().start(); print(p.chromium.executable_path); p.stop()'
if ($LASTEXITCODE -ne 0) { throw 'Không xác định được Chromium.' }
$env:REVOLAND_BUILD_CHROMIUM = Split-Path -Parent (Split-Path -Parent $browserExe.Trim())
if (-not (Test-Path -LiteralPath $browserExe.Trim())) { throw 'Chạy python -m playwright install chromium trước.' }
& $pythonPath -m PyInstaller --noconfirm --distpath $releasePath --workpath .cache\build-current packaging\RevolandFBPoster.spec
if ($LASTEXITCODE -ne 0) { throw 'Build EXE thất bại.' }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'packaging\HUONG_DAN_CHAY_EXE.txt') -Destination (Join-Path $releasePath 'HUONG_DAN_CHAY_EXE.txt')
Write-Host 'Đã tạo dist\revoland-link-v18\CongCuBDS_JSON.exe'

