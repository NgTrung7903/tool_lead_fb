@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if /i "%~1"=="--dev" (
    shift
    goto :dev_menu
)
if /i "%~1"=="--menu" (
    shift
    goto :dev_menu
)

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" desktop_launcher.py %*
    if errorlevel 1 pause
    exit /b %errorlevel%
)

if exist "dist\revoland-link-v18\CongCuBDS_JSON.exe" (
    "dist\revoland-link-v18\CongCuBDS_JSON.exe" %*
    exit /b %errorlevel%
)

echo Khong tim thay ban EXE moi nhat hoac moi truong Python (.venv).
echo Dang tu dong cai dat moi truong lan dau (can Python 3.12+ va Internet)...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 (
    echo.
    echo Cai dat that bai. Hay dung file dist\revoland-link-v18\CongCuBDS_JSON.exe hoac lien he ho tro ky thuat.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" desktop_launcher.py %*
if errorlevel 1 pause
exit /b %errorlevel%

:dev_menu
if not exist ".venv\Scripts\python.exe" (
    echo Chua co .venv. Chay install.ps1 truoc.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" menu.py %*
exit /b %errorlevel%


