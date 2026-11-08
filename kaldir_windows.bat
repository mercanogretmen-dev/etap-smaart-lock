@echo off
chcp 65001 >nul
title Tahta Kilit — Windows Kaldırma
echo ======================================================================
echo   🗑️ TAHTA KİLİT — Windows Kaldırma Sihirbazı
echo   Geliştirici: MERCAN ROBOTİK
echo ======================================================================
echo.

echo 🛑 1/3: Çalışan kilit ekranı kapatılıyor...
taskkill /f /im pythonw.exe /fi "WINDOWTITLE eq TAHTA KİLİT*" >nul 2>&1
taskkill /f /im TahtaKilit.exe >nul 2>&1

echo 🗑️ 2/3: Kısayollar ve başlangıç kayıtları siliniyor...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$desk = [Environment]::GetFolderPath('Desktop'); " ^
    "$start = [Environment]::GetFolderPath('Startup'); " ^
    "Remove-Item \"$desk\Tahta Kilit.lnk\" -ErrorAction SilentlyContinue; " ^
    "Remove-Item \"$start\Tahta Kilit.lnk\" -ErrorAction SilentlyContinue; "

echo 📁 3/3: Program ve ayar dosyaları temizleniyor...
set "INSTALL_DIR=%LOCALAPPDATA%\TahtaKilit"
if exist "%INSTALL_DIR%" rmdir /s /q "%INSTALL_DIR%"

set "CONF_DIR1=%APPDATA%\TahtaKilit"
if exist "%CONF_DIR1%" rmdir /s /q "%CONF_DIR1%"

set "CONF_DIR2=%ProgramData%\TahtaKilit"
if exist "%CONF_DIR2%" rmdir /s /q "%CONF_DIR2%"

echo.
echo ======================================================================
echo   ✅ TAHTA KİLİT SİSTEMİNİZDEN TAMAMEN KALDIRILDI!
echo   Masaüstü kısayolları, otomatik başlama ve tüm ayarlar silindi.
echo ======================================================================
echo.
pause
exit /b 0
