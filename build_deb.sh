#!/usr/bin/env bash
# ==============================================================================
# 📦 TAHTA KİLİT — Pardus / Debian (.deb) Kurulum Paketi Üretici Betiği
# Geliştirici: MERCAN ROBOTİK
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VERSION="1.1.0"
PKG_NAME="tahta-kilit_${VERSION}_all"
BUILD_DIR="$SCRIPT_DIR/build_deb_tmp/$PKG_NAME"

echo "===================================================================="
echo "📦 TAHTA KİLİT (.deb) PAKETİ DERLENİYOR..."
echo "   Sürüm: $VERSION"
echo "===================================================================="

# Temizlik
rm -rf "$SCRIPT_DIR/build_deb_tmp"
mkdir -p "$BUILD_DIR/DEBIAN"
mkdir -p "$BUILD_DIR/opt/etap-smartlock/assets"
mkdir -p "$BUILD_DIR/etc/etap-smartlock"
mkdir -p "$BUILD_DIR/etc/xdg/autostart"
mkdir -p "$BUILD_DIR/usr/share/applications"
mkdir -p "$BUILD_DIR/usr/local/bin"

# 1. DEBIAN/control dosyası
cat << EOF > "$BUILD_DIR/DEBIAN/control"
Package: tahta-kilit
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: python3, python3-pyqt6 | python3-pyqt5, python3-qrcode, python3-pil, python3-websockets
Maintainer: Mercan Robotik <iletisim@mercanrobotik.com>
Homepage: https://github.com/mercanogretmen-dev/etap-smaart-lock
Description: Etkileşimli Tahta Kilit ve Mobil Yönetim Sistemi
 Pardus ETAP akıllı tahtalar için geliştirilmiş modern, güvenli hibrit kilit sistemi.
 Geliştirici: Mercan Robotik
EOF

# 2. DEBIAN/postinst (Kurulum sonrası betiği)
cat << 'EOF' > "$BUILD_DIR/DEBIAN/postinst"
#!/usr/bin/env bash
set -e

# Python baytkodu derle (.pyc) ve yetkileri kısıtla
python3 -m compileall -q /opt/etap-smartlock 2>/dev/null || true
chown -R root:root /opt/etap-smartlock
chmod -R 755 /opt/etap-smartlock

# Eski çakışan autostart ve oturum kalıntılarını temizle
rm -f /etc/xdg/autostart/etap-smartlock.desktop 2>/dev/null || true
rm -f /home/*/.config/autostart/etap-smartlock.desktop 2>/dev/null || true
rm -rf /home/*/.cache/sessions/* 2>/dev/null || true

# Kalıcı ayar dosyası oluştur
if [ ! -f /etc/etap-smartlock/config.ini ] && [ -f /opt/etap-smartlock/config.ini.default ]; then
    cp /opt/etap-smartlock/config.ini.default /etc/etap-smartlock/config.ini
    chmod 666 /etc/etap-smartlock/config.ini
fi

# Çalıştırılabilir sistem komutları
ln -sf /opt/etap-smartlock/kilit_ekrani.py /usr/local/bin/tahta-kilit 2>/dev/null || true
chmod 755 /usr/local/bin/tahta-kilit 2>/dev/null || true

echo "✅ Tahta Kilit başarıyla sisteme kuruldu!"
exit 0
EOF
chmod 755 "$BUILD_DIR/DEBIAN/postinst"

# 3. DEBIAN/prerm (Kaldırma öncesi betiği)
cat << 'EOF' > "$BUILD_DIR/DEBIAN/prerm"
#!/usr/bin/env bash
pkill -f kilit_ekrani.py 2>/dev/null || true
exit 0
EOF
chmod 755 "$BUILD_DIR/DEBIAN/prerm"

# 4. Program dosyalarını paket dizinine kopyala
cp -f "$SCRIPT_DIR/client-tahta/kilit_ekrani.py" "$BUILD_DIR/opt/etap-smartlock/"
cp -f "$SCRIPT_DIR/client-tahta/config.ini" "$BUILD_DIR/opt/etap-smartlock/config.ini.default"
cp -rf "$SCRIPT_DIR/client-tahta/assets"/* "$BUILD_DIR/opt/etap-smartlock/assets/"
if [ -f "$SCRIPT_DIR/guncelle.sh" ]; then
    cp -f "$SCRIPT_DIR/guncelle.sh" "$BUILD_DIR/opt/etap-smartlock/guncelle.sh"
    chmod 755 "$BUILD_DIR/opt/etap-smartlock/guncelle.sh"
fi

# 5. Kısayollar ve Başlatıcılar
cat << 'EOF' > "$BUILD_DIR/usr/local/bin/tahta-kilit"
#!/usr/bin/env bash
exec /usr/bin/python3 /opt/etap-smartlock/kilit_ekrani.py "$@"
EOF
chmod 755 "$BUILD_DIR/usr/local/bin/tahta-kilit"

cat << 'EOF' > "$BUILD_DIR/etc/xdg/autostart/tahta-kilit.desktop"
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
chmod 644 "$BUILD_DIR/etc/xdg/autostart/tahta-kilit.desktop"

cat << 'EOF' > "$BUILD_DIR/usr/share/applications/tahta-kilit.desktop"
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
chmod 644 "$BUILD_DIR/usr/share/applications/tahta-kilit.desktop"

# 6. dpkg-deb ile .deb Paketini Üret
echo "🔨 Paket dosyası inşa ediliyor..."
dpkg-deb --build "$BUILD_DIR" "$SCRIPT_DIR/${PKG_NAME}.deb" 2>/dev/null || {
    echo "⚠️ 'dpkg-deb' komutu bulunamadı (Windows ortamı olabilir). Paket taslağı '$BUILD_DIR' altında hazırlandı."
    echo "📌 Pardus/Linux terminalinde 'bash build_deb.sh' çalıştırarak .deb dosyasını doğrudan üretebilirsiniz."
    exit 0
}

rm -rf "$SCRIPT_DIR/build_deb_tmp"
echo "===================================================================="
echo "🎉 .DEB PAKETİ BAŞARIYLA ÜRETİLDİ: ${PKG_NAME}.deb"
echo "📌 Kurmak için Pardus'ta çift tıklayın veya terminalden:"
echo "   sudo dpkg -i ${PKG_NAME}.deb"
echo "===================================================================="
