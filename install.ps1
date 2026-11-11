$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    & py -3 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Cần cài Python 3.12 trở lên và Python Launcher (py).' }
}
& '.\.venv\Scripts\python.exe' -m pip install -r requirements-lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Cài thư viện thất bại. Kiểm tra mạng và phiên bản Python.' }
& '.\.venv\Scripts\python.exe' -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw 'Tải Chromium thất bại. Kiểm tra mạng rồi chạy lại.' }
Write-Host 'Đã cài. Chạy: .\start.ps1 -Customer khach01'
