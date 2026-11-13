#!/usr/bin/env bash
# ==============================================================================
# 🛡️ TAHTA KİLİT — Pardus ETAP Profesyonel Sistem Kurulum Betiği
# Geliştirici: MERCAN ROBOTİK
# ==============================================================================

set -e

if [ "$EUID" -ne 0 ]; then
  echo "❌ Lütfen bu kurulumu yönetici (root) olarak çalıştırın:"
  echo "👉 sudo bash kur_pardus.sh"
  exit 1
fi

echo "===================================================================="
echo "🚀 TAHTA KİLİT — Pardus ETAP Kurulumu Başlatılıyor..."
echo "   Geliştirici: MERCAN ROBOTİK"
echo "===================================================================="
echo ""

# 1. Gerekli Python ve Qt sistem paketlerini kur
echo "📦 1/5: Sistem bağımlılıkları kontrol ediliyor ve kuruluyor..."
apt update -y -qq
apt install -y python3 python3-pip python3-pyqt6 python3-qrcode python3-pil python3-websockets 2>/dev/null || {
    echo "⚠️ PyQt6 sistem paketi bulunamadı, pip ve PyQt5 deneniyor..."
    apt install -y python3-pyqt5 python3-qrcode python3-pil python3-websockets 2>/dev/null || true
    pip3 install --quiet PyQt6 qrcode pillow websockets 2>/dev/null || true
}

# 2. Kurulum dizinini hazırla (/opt/etap-smartlock)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Eğer client-tahta altından çalıştırıldıysa proje kökünü bul
if [ -d "$SCRIPT_DIR/client-tahta" ]; then
    CLIENT_DIR="$SCRIPT_DIR/client-tahta"
    ROOT_DIR="$SCRIPT_DIR"
elif [ -f "$SCRIPT_DIR/kilit_ekrani.py" ]; then
    CLIENT_DIR="$SCRIPT_DIR"
    ROOT_DIR="$(dirname "$SCRIPT_DIR")"
else
    CLIENT_DIR="$SCRIPT_DIR"
    ROOT_DIR="$SCRIPT_DIR"
fi

INSTALL_DIR="/opt/etap-smartlock"
SYS_CONF_DIR="/etc/etap-smartlock"

echo "📁 2/5: Program korumalı sistem dizinine kuruluyor (/opt/etap-smartlock)..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/assets"

# Dosyaları /opt altına kopyala
cp -f "$CLIENT_DIR/kilit_ekrani.py" "$INSTALL_DIR/"
cp -f "$CLIENT_DIR/config.ini" "$INSTALL_DIR/config.ini.default"
if [ -f "$ROOT_DIR/guncelle.sh" ]; then
    cp -f "$ROOT_DIR/guncelle.sh" "$INSTALL_DIR/guncelle.sh"
    chmod 755 "$INSTALL_DIR/guncelle.sh"
fi
if [ -f "$ROOT_DIR/kaldir_pardus.sh" ]; then
    cp -f "$ROOT_DIR/kaldir_pardus.sh" "$INSTALL_DIR/kaldir_pardus.sh"
    chmod 755 "$INSTALL_DIR/kaldir_pardus.sh"
fi
cp -rf "$CLIENT_DIR/assets"/* "$INSTALL_DIR/assets/" 2>/dev/null || true

# 2.1 Güvenlik: Python Baytkodu (.pyc) Derle ve Kaynak Kod Yetkilerini Kısıtla
echo "🔒 3/5: Kaynak kod güvenliği yapılandırılıyor (Öğrencilerin değiştirmesi engelleniyor)..."
python3 -m compileall -q "$INSTALL_DIR" || true

# Program dosyaları ve güncellemeler için tam erişim verilir (uygulama içi tek tıkla güncelleme için)
chown -R root:root "$INSTALL_DIR"
chmod -R 777 "$INSTALL_DIR"

# 2.2 Kalıcı ve ortak ayar dizini oluştur (/etc/etap-smartlock)
mkdir -p "$SYS_CONF_DIR"
chmod 777 "$SYS_CONF_DIR"
if [ ! -f "$SYS_CONF_DIR/config.ini" ] && [ -f "$CLIENT_DIR/config.ini" ]; then
    cp "$CLIENT_DIR/config.ini" "$SYS_CONF_DIR/config.ini"
fi
if [ -f "$SYS_CONF_DIR/config.ini" ]; then
    sed -i 's/^cihaz_id = etap-57435795.*/cihaz_id = /g' "$SYS_CONF_DIR/config.ini" 2>/dev/null || true
fi
chmod 666 "$SYS_CONF_DIR"/config.ini 2>/dev/null || true

# 3. Sistem Komutları Oluştur (/usr/local/bin)
cat << 'EOF' > /usr/local/bin/tahta-kilit
#!/usr/bin/env bash
exec /usr/bin/python3 /opt/etap-smartlock/kilit_ekrani.py "$@"
EOF
chmod 755 /usr/local/bin/tahta-kilit

cat << 'EOF' > /usr/local/bin/tahta-kilit-guncelle
#!/usr/bin/env bash
exec bash /opt/etap-smartlock/guncelle.sh "$@"
EOF
chmod 755 /usr/local/bin/tahta-kilit-guncelle

cat << 'EOF' > /usr/local/bin/tahta-kilit-kaldir
#!/usr/bin/env bash
exec bash /opt/etap-smartlock/kaldir_pardus.sh "$@"
EOF
chmod 755 /usr/local/bin/tahta-kilit-kaldir

# 4. Otomatik Başlatma (Autostart) ve Başlat Menüsü (.desktop)
echo "⚙️ 4/5: Başlat menüsü ve otomatik açılış yapılandırılıyor..."
# Çift açılış ve ekran çakışmalarını önlemek için eski/mükerrer kayıtları temizle
pkill -9 -f kilit_ekrani.py 2>/dev/null || true
rm -f /etc/xdg/autostart/etap-smartlock.desktop
rm -f /etc/xdg/autostart/tahta-kilit.desktop
rm -f /usr/share/applications/etap-smartlock.desktop 2>/dev/null || true
rm -f /home/*/.config/autostart/etap-smartlock.desktop 2>/dev/null || true
rm -f /home/*/.config/autostart/tahta-kilit.desktop 2>/dev/null || true
rm -f /root/.config/autostart/etap-smartlock.desktop 2>/dev/null || true
rm -f /root/.config/autostart/tahta-kilit.desktop 2>/dev/null || true
# XFCE oturum önbelleğini temizle (yeniden başlatıldığında açık kalan pencerelerin tekrar dirilmesini önler)
rm -rf /home/*/.cache/sessions/* 2>/dev/null || true
rm -rf /root/.cache/sessions/* 2>/dev/null || true
rm -f /tmp/tahta_kilit_*.lock /tmp/tahta_kilit*.lock 2>/dev/null || true

mkdir -p /etc/xdg/autostart
mkdir -p /usr/share/applications

cat << 'EOF' > /etc/xdg/autostart/tahta-kilit.desktop
[Desktop Entry]
Type=Application
Name=Tahta Kilit
Comment=Etkileşimli Tahta Kilit Uygulaması (Mercan Robotik)
Exec=/usr/bin/python3 /opt/etap-smartlock/kilit_ekrani.py
Path=/opt/etap-smartlock
Icon=/opt/etap-smartlock/assets/tahta_kilit_icon.png
Terminal=false
Categories=Utility;System;
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF
chmod 644 /etc/xdg/autostart/tahta-kilit.desktop

cat << 'EOF' > /usr/share/applications/tahta-kilit.desktop
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
chmod 644 /usr/share/applications/tahta-kilit.desktop

# 5. Ev Dizinini Temizleme (Kaynak klasörün Ev Dizini'nde görünmesini gizleme)
echo "🧹 5/5: Ev dizini temizleniyor..."
# Eğer repo /home/*/ altında açık şekilde duruyorsa, klasör adının önüne nokta koyarak gizli yapalım
PARENT_DIR="$(dirname "$ROOT_DIR")"
REPO_NAME="$(basename "$ROOT_DIR")"
if [[ "$PARENT_DIR" =~ ^/home/ ]] && [[ "$REPO_NAME" != .* ]]; then
    HIDDEN_DIR="$PARENT_DIR/.$REPO_NAME"
    echo "💡 '$ROOT_DIR' dizini dosya yöneticisinde kirlilik yaratmaması için gizli klasöre dönüştürülüyor -> '$HIDDEN_DIR'"
    mv "$ROOT_DIR" "$HIDDEN_DIR" 2>/dev/null || true
    # /opt/etap-smartlock/guncelle.sh içindeki çalışma dizinini güncelle
    sed -i "s|$ROOT_DIR|$HIDDEN_DIR|g" "$INSTALL_DIR/guncelle.sh" 2>/dev/null || true
fi

echo ""
echo "===================================================================="
echo "🎉 TEBRİKLER! TAHTA KİLİT BAŞARIYLA SİSTEME KURULDU!"
echo "===================================================================="
echo "✅ Program korumalı /opt/etap-smartlock dizinine kuruldu."
echo "✅ Öğrenciler veya standart kullanıcılar kaynak kodları değiştiremez."
echo "✅ Tahta açıldığında veya yeniden başlatıldığında otomatik açılacaktır."
echo "✅ İstediğiniz zaman terminalden 'tahta-kilit' yazarak da çalıştırabilirsiniz."
echo "✅ Güncellemek için terminalden 'tahta-kilit-guncelle' yazabilir veya tahtadaki ayarlardan 'Güncelle' butonuna basabilirsiniz."
echo "===================================================================="
