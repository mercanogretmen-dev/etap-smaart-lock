#!/usr/bin/env bash
# ==============================================================================
# ETAP Akıllı Kilit & Mobil Yönetim Sistemi — Pardus ETAP Kurulum Betiği
# ==============================================================================

set -e

if [ "$EUID" -ne 0 ]; then
  echo "❌ Lütfen bu kurulumu yönetici olarak çalıştırın: sudo bash kur_pardus.sh"
  exit 1
fi

echo "🚀 Pardus ETAP Akıllı Kilit Kurulumu Başlatılıyor..."

# 1. Gerekli Python ve Qt sistem paketlerini kur
echo "📦 Sistem paketleri güncelleniyor ve bağımlılıklar kuruluyor..."
apt update -y
apt install -y python3 python3-pip python3-pyqt6 python3-qrcode python3-pil python3-websockets || {
    echo "⚠️ PyQt6 bulunamadı, PyQt5 deneniyor..."
    apt install -y python3-pyqt5 python3-qrcode python3-pil python3-websockets
}

# 2. Kurulum dizinini hazırla
INSTALL_DIR="/opt/etap-smartlock"
echo "📁 Program dosyaları ${INSTALL_DIR} dizinine kopyalanıyor..."
mkdir -p "$INSTALL_DIR"
cp -r ./* "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/kilit_ekrani.py"
chmod -R 777 "$INSTALL_DIR"

# 3. Otomatik Başlatma (Autostart) Kaydı Oluştur
AUTOSTART_FILE="/etc/xdg/autostart/etap-smartlock.desktop"
echo "⚙️ Otomatik başlatma yapılandırılıyor: ${AUTOSTART_FILE}"

cat << 'EOF' > "$AUTOSTART_FILE"
[Desktop Entry]
Type=Application
Name=ETAP Akıllı Kilit
Comment=Pardus ETAP Akıllı Tahta Kilit Sistemi
Exec=python3 /opt/etap-smartlock/kilit_ekrani.py
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF

chmod 644 "$AUTOSTART_FILE"

# 4. Masaüstü Kısayolu ve Menü Girişi
DESKTOP_ENTRY="/usr/share/applications/etap-smartlock.desktop"
cat << 'EOF' > "$DESKTOP_ENTRY"
[Desktop Entry]
Type=Application
Name=ETAP Akıllı Kilit
Comment=Akıllı Tahta Kilit Sistemi
Exec=python3 /opt/etap-smartlock/kilit_ekrani.py
Icon=system-lock-screen
Terminal=false
Categories=Utility;System;
EOF

chmod 644 "$DESKTOP_ENTRY"

echo "===================================================================="
echo "✅ KURULUM BAŞARIYLA TAMAMLANDI!"
echo "📌 Tahta yeniden başlatıldığında kilit ekranı otomatik olarak açılacaktır."
echo "📌 Hemen test etmek için: python3 /opt/etap-smartlock/kilit_ekrani.py"
echo "===================================================================="
