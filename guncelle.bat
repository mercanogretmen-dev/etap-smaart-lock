@echo off
chcp 65001 >nul
title Tahta Kilit — Güncelleme
echo ======================================================================
echo   🔄 TAHTA KİLİT — Windows Güncelleme
echo   Geliştirici: MERCAN ROBOTİK
echo ======================================================================
echo.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: 1. Çalışan kilit ekranı varsa kapat
echo 🛑 Çalışan kilit ekranı kapatılıyor...
taskkill /f /im pythonw.exe /fi "WINDOWTITLE eq TAHTA KİLİT*" >nul 2>&1
taskkill /f /im TahtaKilit.exe >nul 2>&1
timeout /t 1 /nobreak >nul

:: 2. Git deposu kontrolü
if exist ".git" (
    echo 📥 GitHub'dan güncellemeler çekiliyor...
    git fetch origin main
    git reset --hard origin/main
    echo ✅ Kodlar güncellendi.
) else (
    echo ℹ️ Git dizini bulunamadı, yerel dosyalar uygulanıyor...
)

:: 3. Kurulu dizini güncelle
set "INSTALL_DIR=%LOCALAPPDATA%\TahtaKilit"
if exist "%INSTALL_DIR%" (
    echo 📁 Kurulu dosyalar yenileniyor...
    copy /y "%SCRIPT_DIR%client-tahta\kilit_ekrani.py" "%INSTALL_DIR%\" >nul
    xcopy /y /e /i "%SCRIPT_DIR%client-tahta\assets\*" "%INSTALL_DIR%\assets\" >nul
    echo ✅ Kurulum güncellendi.
)

echo.
echo ======================================================================
echo   🎉 GÜNCELLEME TAMAMLANDI!
echo   Kilit ekranı yeniden başlatılıyor...
echo ======================================================================
start "" pythonw "%INSTALL_DIR%\kilit_ekrani.py"
timeout /t 2 /nobreak >nul
exit /b 0
