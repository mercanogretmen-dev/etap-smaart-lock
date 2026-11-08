#!/usr/bin/env bash
# ==============================================================================
# 🗑️ TAHTA KİLİT — Pardus ETAP Tamamen Kaldırma (Uninstall) Betiği
# Geliştirici: MERCAN ROBOTİK
# ==============================================================================

set -e

if [ "$EUID" -ne 0 ]; then
  echo "❌ Lütfen kaldırma işlemini yönetici (root) olarak çalıştırın:"
  echo "👉 sudo bash kaldir_pardus.sh"
  exit 1
fi

echo "===================================================================="
echo "🗑️ TAHTA KİLİT — Pardus ETAP Kaldırma Sihirbazı"
echo "===================================================================="
echo ""

# 1. Çalışan kilit ekranı süreçlerini sonlandır
echo "🛑 1/6: Çalışan kilit ekranı kapatılıyor..."
pkill -9 -f kilit_ekrani.py 2>/dev/null || true
pkill -9 -f tahta-kilit 2>/dev/null || true
sleep 1

# 2. Otomatik başlatma (Autostart) kayıtlarını sil
echo "🚫 2/6: Açılışta otomatik başlama kayıtları siliniyor..."
rm -f /etc/xdg/autostart/tahta-kilit.desktop
rm -f /etc/xdg/autostart/etap-smartlock.desktop
rm -f /home/*/.config/autostart/tahta-kilit.desktop 2>/dev/null || true
rm -f /home/*/.config/autostart/etap-smartlock.desktop 2>/dev/null || true
rm -f /root/.config/autostart/tahta-kilit.desktop 2>/dev/null || true
rm -f /root/.config/autostart/etap-smartlock.desktop 2>/dev/null || true
# XFCE oturum önbelleğini ve kilit dosyalarını temizle
rm -rf /home/*/.cache/sessions/* 2>/dev/null || true
rm -rf /root/.cache/sessions/* 2>/dev/null || true
rm -f /tmp/tahta_kilit_*.lock /tmp/tahta_kilit*.lock 2>/dev/null || true

# 3. Başlat Menüsü (.desktop) kısayollarını sil
echo "🗑️ 3/6: Pardus Başlat Menüsü kısayolları kaldırılıyor..."
rm -f /usr/share/applications/tahta-kilit.desktop
rm -f /usr/share/applications/etap-smartlock.desktop
rm -f /home/*/.local/share/applications/tahta-kilit.desktop 2>/dev/null || true

# 4. Sistem komutlarını sil (/usr/local/bin)
echo "🧹 4/6: Sistem komutları (/usr/local/bin) temizleniyor..."
rm -f /usr/local/bin/tahta-kilit
rm -f /usr/local/bin/tahta-kilit-guncelle
rm -f /usr/local/bin/tahta-kilit-kaldir

# 5. Program dosyalarını sil (/opt)
echo "📁 5/6: Kurulum dizini siliniyor (/opt/etap-smartlock)..."
rm -rf /opt/etap-smartlock
rm -rf /opt/tahta-kilit

# Eğer .deb paketi olarak kuruluysa dpkg'den de temizle
if dpkg -s tahta-kilit >/dev/null 2>&1; then
    dpkg --purge tahta-kilit 2>/dev/null || true
fi

# 6. Ayar ve Yapılandırma Dosyalarını Temizleme
echo "⚙️ 6/6: Yapılandırma ve önbellek dosyaları temizleniyor..."
rm -rf /etc/etap-smartlock
rm -rf /home/*/.config/etap-smartlock 2>/dev/null || true

# Masaüstü ve menü veritabanını tazele
update-desktop-database 2>/dev/null || true

echo ""
echo "===================================================================="
echo "✅ TAHTA KİLİT SİSTEMDEN TAMAMEN KALDIRILDI!"
echo "===================================================================="
echo "📌 Otomatik başlama iptal edildi, tüm sistem dosyaları temizlendi."
echo "📌 İsteğe bağlı: İndirdiğiniz kaynak kod klasörünü silmek için:"
echo "   rm -rf ~/etap-smaart-lock ~/.etap-smartlock"
echo "===================================================================="
