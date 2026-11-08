@echo off
chcp 65001 >nul
title Tahta Kilit — Windows Kaldırma
echo ======================================================================
echo   🗑️ TAHTA KİLİT — Windows Kaldırma Sihirbazı
echo ======================================================================
echo.

echo 🛑 Çalışan kilit ekranı kapatılıyor...
taskkill /f /im pythonw.exe /fi "WINDOWTITLE eq TAHTA KİLİT*" >nul 2>&1
taskkill /f /im TahtaKilit.exe >nul 2>&1

echo 🗑️ Kısayollar ve başlangıç kayıtları siliniyor...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$desk = [Environment]::GetFolderPath('Desktop'); " ^
    "$start = [Environment]::GetFolderPath('Startup'); " ^
    "Remove-Item \"$desk\Tahta Kilit.lnk\" -ErrorAction SilentlyContinue; " ^
    "Remove-Item \"$start\Tahta Kilit.lnk\" -ErrorAction SilentlyContinue; "

set "INSTALL_DIR=%LOCALAPPDATA%\TahtaKilit"
if exist "%INSTALL_DIR%" (
    echo 📁 Dosyalar siliniyor: %INSTALL_DIR%
    rmdir /s /q "%INSTALL_DIR%"
)

echo.
echo ✅ Tahta Kilit sisteminizden tamamen kaldırıldı.
pause
exit /b 0
