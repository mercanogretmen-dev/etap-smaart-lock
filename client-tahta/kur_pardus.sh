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
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/etap-smartlock"
SYS_CONF_DIR="/etc/etap-smartlock"

echo "📁 Program dosyaları ${INSTALL_DIR} dizinine kopyalanıyor..."
mkdir -p "$INSTALL_DIR"
cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/kilit_ekrani.py"
chmod -R 777 "$INSTALL_DIR"
chmod 666 "$INSTALL_DIR"/config.ini 2>/dev/null || true

# 2.1 Kalıcı ve ortak ayar dizini oluştur (/etc/etap-smartlock)
# Bu dizin hem ogretmen hem de etapadmin kullanıcıları tarafından yazılabilir olmalıdır
mkdir -p "$SYS_CONF_DIR"
chmod 777 "$SYS_CONF_DIR"
if [ ! -f "$SYS_CONF_DIR/config.ini" ] && [ -f "$SCRIPT_DIR/config.ini" ]; then
    cp "$SCRIPT_DIR/config.ini" "$SYS_CONF_DIR/config.ini"
fi
chmod 666 "$SYS_CONF_DIR"/config.ini 2>/dev/null || true

# 3. Otomatik Başlatma (Autostart) Kaydı Oluştur
AUTOSTART_FILE="/etc/xdg/autostart/etap-smartlock.desktop"
echo "⚙️ Otomatik başlatma yapılandırılıyor: ${AUTOSTART_FILE}"

cat << 'EOF' > "$AUTOSTART_FILE"
[Desktop Entry]
Type=Application
Name=Tahta Kilit
Comment=Etkileşimli Tahta Kilit Uygulaması (Mercan Robotik)
Exec=/usr/bin/python3 /opt/etap-smartlock/kilit_ekrani.py
Path=/opt/etap-smartlock
Icon=/opt/etap-smartlock/assets/tahta_kilit_icon.png
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
Name=Tahta Kilit
Comment=Etkileşimli Tahta Kilit Uygulaması (Mercan Robotik)
Exec=/usr/bin/python3 /opt/etap-smartlock/kilit_ekrani.py
Path=/opt/etap-smartlock
Icon=/opt/etap-smartlock/assets/tahta_kilit_icon.png
Terminal=false
Categories=Utility;System;
EOF

chmod 644 "$DESKTOP_ENTRY"

echo "===================================================================="
echo "✅ KURULUM BAŞARIYLA TAMAMLANDI!"
echo "📌 Tahta yeniden başlatıldığında kilit ekranı otomatik olarak açılacaktır."
echo "📌 Hemen test etmek için: python3 /opt/etap-smartlock/kilit_ekrani.py"
echo "===================================================================="
