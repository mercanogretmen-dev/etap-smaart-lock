#!/usr/bin/env bash
# ==============================================================================
# 🔄 TAHTA KİLİT — Hızlı Güncelleme ve Yeniden Başlatma Betiği
# Geliştirici: MERCAN ROBOTİK
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Git deposunun bulunduğu dizini bul
REPO_DIR="$SCRIPT_DIR"
if [ ! -d "$REPO_DIR/.git" ]; then
    for candidate in "$HOME/etap-smaart-lock" "$HOME/.etap-smartlock" "$HOME/.etap-smaart-lock" "/opt/etap-smartlock-repo"; do
        if [ -d "$candidate/.git" ]; then
            REPO_DIR="$candidate"
            break
        fi
    done
fi

echo "========================================================"
echo "🔄 TAHTA KİLİT GÜNCELLENİYOR..."
echo "   Çalışma Dizini: $REPO_DIR"
echo "========================================================"

# 1. Çalışan eski kilit ekranını kapat
echo "🛑 1/3: Çalışan kilit ekranı durduruluyor..."
sudo pkill -9 -f kilit_ekrani.py 2>/dev/null || true
sudo pkill -9 -f tahta-kilit 2>/dev/null || true
rm -f /tmp/tahta_kilit_*.lock /tmp/tahta_kilit*.lock 2>/dev/null || true
sleep 1

# 2. GitHub'dan en son kodları çek
cd "$REPO_DIR"
echo "📥 2/3: GitHub'dan en güncel sürüm çekiliyor..."
git fetch origin main
git reset --hard origin/main

# 3. Kurulum betiğini çalıştır ve sistemi güncelle
echo "⚙️ 3/3: Yeni dosyalar sisteme uygulanıyor..."
if [ -f "$REPO_DIR/kur_pardus.sh" ]; then
    sudo bash "$REPO_DIR/kur_pardus.sh"
elif [ -f "$REPO_DIR/client-tahta/kur_pardus.sh" ]; then
    sudo bash "$REPO_DIR/client-tahta/kur_pardus.sh"
fi

echo "========================================================"
echo "✅ GÜNCELLEME BAŞARIYLA TAMAMLANDI!"
echo "🚀 Kilit ekranı başlatılıyor..."
echo "========================================================"

# Kilit ekranını mevcut kullanıcı oturumunda arka planda başlat
if [ -n "$DISPLAY" ]; then
    nohup python3 /opt/etap-smartlock/kilit_ekrani.py > /dev/null 2>&1 &
fi
