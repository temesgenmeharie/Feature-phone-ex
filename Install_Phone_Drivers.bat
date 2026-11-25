@echo off
setlocal enabledelayedexpansion

:: Check for Administrator privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting Administrator privileges to install USB COM Drivers...
    powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/c \"\"%~dpnx0\"\"' -Verb RunAs"
    exit /b
)

title Feature Phone Forensic Driver Installer
color 0A
echo =====================================================================
echo    FEATURE PHONE FORENSIC DRIVER INSTALLER (MediaTek & Spreadtrum)
echo =====================================================================
echo.
echo Target INF: "%~dp0drivers\featurephone_vcom.inf"
echo.

if not exist "%~dp0drivers\featurephone_vcom.inf" (
    echo [ERROR] Driver INF file not found at "%~dp0drivers\featurephone_vcom.inf"
    pause
    exit /b 1
)

echo [1/3] Adding driver package to Windows Driver Store...
pnputil /add-driver "%~dp0drivers\featurephone_vcom.inf" /install
if %errorlevel% neq 0 (
    echo [WARNING] pnputil returned non-zero code %errorlevel%. Continuing to device scan...
)

echo.
echo [2/3] Rescanning Plug and Play device tree...
pnputil /scan-devices

echo.
echo [3/3] Checking connected phone COM ports...
powershell -NoProfile -Command "[System.IO.Ports.SerialPort]::GetPortNames() | ForEach-Object { Write-Host '  Found Active Port:' $_ }"

echo.
echo =====================================================================
echo [SUCCESS] Drivers installed successfully!
echo Windows will now automatically assign a COM port to your feature phone.
echo You can return to the web application and click 'Refresh Ports'.
echo =====================================================================
echo.
pause

