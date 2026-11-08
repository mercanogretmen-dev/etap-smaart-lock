@echo off
chcp 65001 >nul
title Tahta Kilit — Windows .EXE Derleyici
echo ======================================================================
echo   🔨 TAHTA KİLİT — Standart Windows (.EXE) Derleme Sihirbazı
echo   PyInstaller ile bağımsız, tek parça çalıştırılabilir dosya üretir.
echo   Geliştirici: MERCAN ROBOTİK
echo ======================================================================
echo.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: PyInstaller kontrolü
pyinstaller --version >nul 2>&1
if %errorlevel% neq 0 (
    echo 📦 PyInstaller kuruluyor...
    pip install pyinstaller
)

echo ⚙️ TahtaKilit.exe derleniyor (Bu işlem 30-60 saniye sürebilir)...
pyinstaller --noconsole --onefile ^
    --icon="%SCRIPT_DIR%client-tahta\assets\tahta_kilit_icon.ico" ^
    --name="TahtaKilit" ^
    --add-data="%SCRIPT_DIR%client-tahta\assets;assets" ^
    --clean ^
    "%SCRIPT_DIR%client-tahta\kilit_ekrani.py"

if exist "dist\TahtaKilit.exe" (
    echo.
    echo ======================================================================
    echo   🎉 DERLEME BAŞARILI!
    echo   Üretilen dosya: dist\TahtaKilit.exe
    echo   Bu .exe dosyasını herhangi bir Windows bilgisayarda doğrudan çalıştırabilirsiniz!
    echo ======================================================================
) else (
    echo ❌ Derleme sırasında bir hata oluştu!
)
pause
exit /b 0
