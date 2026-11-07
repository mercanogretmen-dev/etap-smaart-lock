#!/usr/bin/env bash
# ==============================================================================
# ETAP Akıllı Kilit — Hızlı Güncelleme ve Yeniden Başlatma Betiği
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================================"
echo "🔄 ETAP Akıllı Kilit Güncelleniyor..."
echo "========================================================"

# 1. Çalışan eski kilit ekranını kapat
echo "🛑 Eski kilit ekranı durduruluyor..."
sudo pkill -f kilit_ekrani.py || true
sleep 1

# 2. GitHub'dan en son kodları çek (Yerel config.ini çakışmalarını otomatik temizle; asıl ayarlar /etc ve ~/.config altındadır)
echo "📥 GitHub'dan güncellemeler çekiliyor..."
git fetch origin main
git reset --hard origin/main

# 3. Kurulum betiğini çalıştır ve sistemi güncelle
echo "⚙️ Yeni dosyalar sisteme uygulanıyor..."
sudo bash "$SCRIPT_DIR/client-tahta/kur_pardus.sh"

echo "========================================================"
echo "✅ GÜNCELLEME BAŞARIYLA TAMAMLANDI!"
echo "🚀 Kilit ekranı başlatılıyor..."
echo "========================================================"

# Kilit ekranını mevcut kullanıcı oturumunda arka planda başlat
nohup python3 /opt/etap-smartlock/kilit_ekrani.py > /dev/null 2>&1 &
