@echo off
title ETAP Akilli Kilit Ekrani
cd /d "%~dp0"
echo ===================================================
echo ETAP Akilli Kilit Ekrani Baslatiliyor...
echo (Cikmak icin klavyeden Ctrl+Q tuslarina basabilirsiniz)
echo ===================================================
python client-tahta/kilit_ekrani.py
pause
