param(
    [ValidatePattern('^[a-zA-Z0-9_-]{1,48}$')][string]$Customer = 'default',
    [ValidateRange(1024,65535)][int]$Port = 8000
)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Chạy install.ps1 trước để cài môi trường Python.' }
# Keep customer sessions outside source control and cloud-synced source folders.
$customerRoot = Join-Path $env:LOCALAPPDATA "RevolandFBPoster\$Customer"
New-Item -ItemType Directory -Path $customerRoot -Force | Out-Null
$userSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls.exe $customerRoot /inheritance:r /grant:r "*${userSid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Không thiết lập được quyền riêng tư cho thư mục khách.' }
$env:REVOLAND_DATA_DIR = $customerRoot
Write-Host "Khách: $Customer | Dữ liệu: $customerRoot | Dashboard: http://127.0.0.1:$Port"
& $pythonPath (Join-Path $projectRoot 'cli.py') --server --port $Port
exit $LASTEXITCODE
