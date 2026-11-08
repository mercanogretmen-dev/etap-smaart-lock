@echo off
chcp 65001 >nul
title Tahta Kilit — Windows Kurulumu
echo ======================================================================
echo   🛡️ TAHTA KİLİT — Windows Otomatik Kurulum Sihirbazı
echo   Geliştirici: MERCAN ROBOTİK
echo ======================================================================
echo.

:: 1. Python Kontrolü
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python sisteminizde bulunamadı!
    echo 📌 Lütfen https://www.python.org/ adresinden Python 3.10+ kurup tekrar deneyin.
    echo ⚠️ Kurulumda 'Add Python to PATH' seçeneğini işaretlemeyi unutmayın.
    pause
    exit /b 1
)

echo ✅ Python bulundu.
echo.

:: 2. Gerekli Kütüphanelerin Kurulumu
echo 📦 Gerekli Python kütüphaneleri kontrol ediliyor ve kuruluyor...
pip install -r "%~dp0client-tahta\requirements.txt" --quiet
if %errorlevel% neq 0 (
    echo ⚠️ Kütüphane yüklemesinde uyarı alındı, devam ediliyor...
)
echo ✅ Kütüphaneler hazır.
echo.

:: 3. Kurulum Dizinini Belirle
set "INSTALL_DIR=%LOCALAPPDATA%\TahtaKilit"
echo 📁 Kurulum dizini: %INSTALL_DIR%
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
if not exist "%INSTALL_DIR%\assets" mkdir "%INSTALL_DIR%\assets"

:: Dosyaları kopyala
copy /y "%~dp0client-tahta\kilit_ekrani.py" "%INSTALL_DIR%\" >nul
copy /y "%~dp0client-tahta\config.ini" "%INSTALL_DIR%\" >nul
copy /y "%~dp0guncelle.bat" "%INSTALL_DIR%\" >nul
xcopy /y /e /i "%~dp0client-tahta\assets\*" "%INSTALL_DIR%\assets\" >nul

echo ✅ Program dosyaları kopyalandı.
echo.

:: 4. Masaüstü ve Başlangıç Kısayolları Oluştur (PowerShell ile .lnk)
echo 🔗 Kısayollar oluşturuluyor...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ws = New-Object -ComObject WScript.Shell; " ^
    "$desk = [Environment]::GetFolderPath('Desktop'); " ^
    "$s1 = $ws.CreateShortcut(\"$desk\Tahta Kilit.lnk\"); " ^
    "$s1.TargetPath = 'pythonw.exe'; " ^
    "$s1.Arguments = '\"%INSTALL_DIR%\kilit_ekrani.py\"'; " ^
    "$s1.WorkingDirectory = '%INSTALL_DIR%'; " ^
    "$s1.IconLocation = '%INSTALL_DIR%\assets\tahta_kilit_icon.ico,0'; " ^
    "$s1.Save(); " ^
    "$start = [Environment]::GetFolderPath('Startup'); " ^
    "$s2 = $ws.CreateShortcut(\"$start\Tahta Kilit.lnk\"); " ^
    "$s2.TargetPath = 'pythonw.exe'; " ^
    "$s2.Arguments = '\"%INSTALL_DIR%\kilit_ekrani.py\"'; " ^
    "$s2.WorkingDirectory = '%INSTALL_DIR%'; " ^
    "$s2.IconLocation = '%INSTALL_DIR%\assets\tahta_kilit_icon.ico,0'; " ^
    "$s2.Save(); "

echo ✅ Masaüstüne 'Tahta Kilit' kısayolu eklendi.
echo ✅ Windows Başlangıç klasörüne eklendi (Bilgisayar açılınca otomatik başlar).
echo.

echo ======================================================================
echo   🎉 KURULUM TAMAMLANDI!
echo   Masaüstündeki 'Tahta Kilit' kısayolundan uygulamayı başlatabilirsiniz.
echo ======================================================================
echo.
set /p START_NOW="Kilit ekranını şimdi başlatmak ister misiniz? (E/H): "
if /i "%START_NOW%"=="E" (
    start "" pythonw "%INSTALL_DIR%\kilit_ekrani.py"
)
exit /b 0
