# ETAP Akıllı Kilit & Mobil Yönetim Sistemi — Proje Hafızası

Bu dosya, projenin bağlamını ve alınan mimari kararları yeni sohbet oturumlarına aktarmak için oluşturulmuştur.

## 📌 Proje Özeti & Özellikler
Pardus ETAP yüklü akıllı tahtalar için geliştirilen hibrit kilit, uzaktan yönetim ve anons sistemi:
1. **Online Mod (Normal):** Telefon 4.5G ile Render'daki Docker sunucusuna bağlanır, QR okutulunca tahta dokunulmadan otomatik açılır.
2. **Offline Mod (Yedek/Acil & Güvenlik):** İnternet kesilirse tahtadaki dokunmatik ekrana Öğretmen PIN kodu (`1234`) veya 30 saniyelik dinamik TOTP kodu girilerek açılır; art arda hatalı PIN denemelerine karşı geçici kilitleme (brute-force koruması) içerir.
3. **Müdür Anons Sistemi:** İdareden gelen acil duyurular tahtanın en üstünde **mavi ışıklı kayan bant (LED Marquee Ticker)** olarak akar; masaüstü açıkken de ayrı duyuru penceresi gösterebilir.
4. **Sınıf Tanımlama:** Tahtadaki ayarlar butonundan yetkili şifresiyle sınıf adı (Örn: `9-A`) kolayca değiştirilebilir.
5. **Müdür / İdare Mobil Paneli (`v1.2.0` – `v1.3.0`):**
   * Okuldaki tahtaların anlık çevrimiçi/çevrimdışı ve kilit durumunu gösteren **Canlı Tahta Filo Panosu**.
   * Tek tıkla toplu işlemler (**Tüm Tahtaları Kilitle / Aç / Kapat - Güç Kes**).
   * Uzaktan anlık **Canlı Ekran Görüntüsü Alma** (`📸 Ekranı Gör`).
   * Mobil panelden merkezi **Okul/Kurum Adı** değiştirme (`server/data/settings.json`) ve tüm tahtalara anında senkronizasyon.
6. **Klon İmaj Koruması / Anti-Cloning (`v1.3.1`):**
   * Fiziksel ağ kartı MAC adresleri (`/sys/class/net/*/address`, `uuid.getnode()`) + BIOS/Anakart DMI parmak izi (`hardware_elements`) ile Clonezilla/DD klon disk imajlarını ilk açılışta otomatik algılayıp benzersiz `etap-<8hex>` ID üretir.
   * Eski klonlanmış/çakışan `etap-57435795` kimliği kara listeye alınmıştır; güncelleme/açılış sırasında otomatik temizlenip yeni donanım ID'si atanır.
   * Tahta Ayarlar penceresinde donanım kimliği görüntülenir ve **"🔄 Kimliği Yenile"** butonu ile tek dokunuşla yenilenebilir.
7. **Paketleme & Tek Tıkla Güncelleme:**
   * `build_deb_package.py` ile saf Python `.deb` paketi üretimi (`tahta-kilit_1.3.1_all.deb` ve `tahta-kilit.deb`).
   * Terminalden `sudo tahta-kilit-guncelle` (`guncelle.sh`) veya tahta Ayarlar menüsünden GitHub üzerinden canlı güncelleme (`version.json`).

## 📂 Dosya Yapısı
* `server/`: FastAPI + WebSockets sunucusu (`main.py`, `config.py`, `data/settings.json`), `Dockerfile` ve `static/` altında mobil telefon arayüzü (PWA/QR okuyucu, `manifest.json`, `sw.js`, mobil ikonlar).
* `client-tahta/`: PyQt6 tam ekran kiosk kilit ekranı (`kilit_ekrani.py`), varsayılan şablon ayarları (`config.ini` — boş `cihaz_id`), Pardus kurulum betiği (`kur_pardus.sh`) ve görseller (`assets/`).
* `build_deb_package.py`, `guncelle.sh`, `kaldir_pardus.sh`, `version.json`: Saf Python Debian (`.deb`) paketleyici, hızlı güncelleme/kaldırma betikleri ve GitHub sürüm bildirimi.
* `tests/test_system.py`: Sunucu API/WebSocket, toplu işlem, canlı ekran görüntüsü ve klon koruma (anti-clone) doğrulamalarını içeren 8 otomatik test.
* `docker-compose.yml`: Yerel Docker testi için.
* `render.yaml`: Render.com ücretsiz bulut dağıtımı için.
* `KULLANIM_KILAVUZU.md`: Adım adım test, kullanım ve iOS/Android PWA mobil kurulum kılavuzu.
* `MEB_VE_RENDER_NOTLARI.md`: Render 15 dk uyku/kota optimizasyonu (cron-job.org) ve MEB Fatih ağı SSL/filtre rehberi.

## 🏷️ Versiyon Takibi & Kararlı Sürümler (Git)
* **`v1.3.1` (Güncel Kararlı Sürüm — Etiket / Tag) — Commit `3e4e367`:** Fiziksel MAC + DMI donanım parmak izi ile Klon İmaj Koruması (Anti-Cloning), `etap-57435795` kara liste temizliği, Ayarlar ekranında `"🔄 Kimliği Yenile"`, canlı ekran görüntüsü (`v1.3.0`), toplu müdür yönetimi (`v1.2.0`–`v1.3.0`) ve 8/8 geçen test paketi.
* **`v1.0.0-stable` (Etiket / Tag) & `stable-v1.0` (Dal / Branch):** Commit `ab744e0` — Kiosk güvenliği (`BypassWindowManagerHint`), dahili katmanlar (Ayarlar, Yönetici Çıkışı, Duyuru), fiziksel + dokunmatik klavye desteği, masaüstü açıkken müdür duyuru penceresi ve iOS/Android PWA mobil arayüzünün tam çalışır, test edilmiş ilk kararlı sürümü.
* **Yerel Yedek Arşivi:** `backups/etap-smart-lock-v1.0.0-stable.zip`
* **İlk Kararlı Sürüme Geri Dönme Komutu:** `git checkout v1.0.0-stable` veya `git reset --hard v1.0.0-stable`
