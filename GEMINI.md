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
7. **Paketleme & Tek Tıkla / Merkezi Güncelleme (`v0.4.0`):**
   * `build_deb_package.py` ile saf Python `.deb` paketi üretimi (`tahta-kilit_0.5.0_all.deb` ve `tahta-kilit.deb`).
   * **Merkezi Uzaktan Güncelleme:** Mobil Müdür Panelinden **"🔄 Tüm Tahtaları Güncelle"** (`POST /api/bulk/update`) veya her tahtanın kartındaki **"🔄 Güncelle"** (`POST /api/board/update`) butonuyla tüm tahtalar aynı anda güncellenebilir; panelde her tahtanın kurulu sürümü (`v0.5.0`) ve canlı güncelleme yüzdesi görünür.
   * **Kilit Ekranında Canlı Güncelleme & Otomatik Kontrol:** Güncelleme sırasında kilit ekranında **"Sistem Güncelleniyor..."** ilerleme kartı (`UpdateProgressOverlayWidget`) — masaüstü açıksa sağ üstte kompakt bant (`DesktopUpdateBanner`) — gösterilir ve işlem bitince uygulama kendini yeniden başlatır. Tahtalar kilitliyken açılışta (25 sn sonra) ve 30 dakikada bir GitHub `version.json` üzerinden daha yeni sürüm kontrolü (`is_newer_version`) yapıp otomatik güncellenir.
   * Terminalden `sudo tahta-kilit-guncelle` (`guncelle.sh`) veya tahta Ayarlar menüsünden GitHub üzerinden canlı güncelleme (`version.json`).
8. **Akıllı Canlı İzleme, Önizleme Duvarı & Tıklanabilir Duyurular (`v0.5.0`):**
   * **Canlı İzleme & Önizleme Duvarı:** Müdür panelinde tekil tahta için **Smart Diff** destekli **`🔴 Canlı İzle`** (`POST /api/board/screenshot` — `720px / kalite 55`, 1.8 sn) ve tüm filo için 2 sütunlu **`📺 Önizleme Duvarı`** (`POST /api/boards/thumbnails` — `320px / kalite 40`, 9 sn) eklenmiştir; değişmeyen karelerde `0 KB` aktarılır ve sekme değişimi / arka plan / 3 dakika zaman aşımıyla kota korunur.
   * **Tıklanabilir Duyurular:** İdare duyuruyla web bağlantısı (`link_url`, `link_label`) gönderebilir; masaüstü açıkken ortada `AnnouncementModalDialog` ve sağ alt kilit butonunun üstünde kalıcı `DesktopAnnouncementWidget`, kilitliyken üst bantta ve kaplama katmanında tıklanınca kilit açılınca otomatik açılan bağlantı desteği yer alır.
   * **Ergonomik Mobil Arayüz:** Ana gezinmede 3 sekme (`Öğretmen`, `PIN`, `İdare`), İdare içinde 2'li hap segment (`Canlı Tahtalar`, `Toplu Yönetim & Duyuru`), Öğretmen sekmesinde 1B Alt Çekmece (`#boardPickerSheet`) ve 4 satırlık sade düzen bulunur.
9. **Yönetici Masaüstüne Dosya Gönderme (`v0.6.0`):**
   * İdare panelindeki **`📁 Masaüstüne Dosya Gönder`** kartından telefonda seçilen `PDF`, `PPTX`, `DOCX`, `XLSX`, `MP3/WAV`, görsel veya küçük video dosyaları (`MP4/WEBM/MKV/MOV` — maks. `25 MB`) tek tahtaya veya tüm okula aktarılabilir.
   * Sunucu 64 KB akışlı yüklemeyi (`POST /api/files/send` → `GET /api/files/download/{file_id}`) `server/data/uploads/` içinde 15 dk TTL + maks. 10 dosya otomatik temizliğiyle yönetir.
   * Tahta istemcisi (`FileDownloadThread`) dosyayı Pardus `~/Masaüstü` / `~/Desktop` klasörüne mevcut dosyaları ezmeden (`dosya (1).pdf`) indirir ve `open_after` seçiliyse hemen (veya kilit açılınca) açar.
10. **İdare Şifre Kapısı, İdareden PIN Değiştirme & Kalıcı Kurum Adı (`v0.7.0`):**
   * Mobil **İdare** sekmesi açılışta şifre giriş kapısı (`#adminLoginGate`, `POST /api/admin/verify`) ile korunur ve tarayıcı `localStorage` içinde idare PIN'ini açık bırakmaz; giriş sonrası **`🔒 Çıkış`** butonuyla oturum kapatılabilir.
   * **İdare → Toplu Yönetim & Duyuru** içinde **`🔐 PIN & Güvenlik Ayarları`** kartı (`POST /api/settings/pins`) yer alır; Öğretmen PIN ve İdare PIN (4–8 rakam) değiştirilip `server/data/settings.json` içinde saklanır, yeni Öğretmen PIN bağlı tahtalara canlı (`update_teacher_pin`) iletilir.
   * Tahta istemcisi ve sunucu WebSocket el sıkışması (`school_name` + `school_name_custom`, `load_config()` çoklu dosya koruması) sayesinde Render uykusundan/yeniden başlatmadan veya istemci yeniden açılışından sonra özelleştirilmiş kurum adı varsayılan MEB adına geri dönmez; ilk bağlanan tahta sunucuyu otomatik iyileştirir (self-healing).

## 📂 Dosya Yapısı
* `server/`: FastAPI + WebSockets sunucusu (`main.py`, `config.py`, `data/settings.json`), `Dockerfile` ve `static/` altında mobil telefon arayüzü (PWA/QR okuyucu, `manifest.json`, `sw.js`, mobil ikonlar).
* `client-tahta/`: PyQt6 tam ekran kiosk kilit ekranı (`kilit_ekrani.py`), varsayılan şablon ayarları (`config.ini` — boş `cihaz_id`), Pardus kurulum betiği (`kur_pardus.sh`) ve görseller (`assets/`).
* `build_deb_package.py`, `guncelle.sh`, `kaldir_pardus.sh`, `version.json`: Saf Python Debian (`.deb`) paketleyici, hızlı güncelleme/kaldırma betikleri ve GitHub sürüm bildirimi.
* `tests/test_system.py`: Sunucu API/WebSocket, idare giriş kapısı ve PIN yönetimi, kurum adı kalıcılığı (self-healing), toplu işlem, canlı izleme/Smart Diff, önizleme duvarı, masaüstüne dosya gönderme, klon koruma (anti-clone) ve merkezi/otomatik güncelleme doğrulamalarını içeren 13 otomatik test.
* `docker-compose.yml`: Yerel Docker testi için.
* `render.yaml`: Render.com ücretsiz bulut dağıtımı için.
* `KULLANIM_KILAVUZU.md`: Adım adım test, kullanım ve iOS/Android PWA mobil kurulum kılavuzu.
* `MEB_VE_RENDER_NOTLARI.md`: Render 15 dk uyku/kota optimizasyonu (cron-job.org) ve MEB Fatih ağı SSL/filtre rehberi.

## 🏷️ Versiyon Takibi, Sürümleme Kuralı & Kararlı Sürümler (Git)
* **Sürümleme Kuralı (`0.x` Serisi):** Kullanıcı açıkça tam kararlı `v1.0.0` sürümüne geçilmesini isteyene kadar tüm özellik sürümleri **`0.x` geliştirme/ön-yayın serisinde** artırılarak ilerler (`v0.4.0` -> `v0.5.0` -> `v0.6.0` -> `v0.7.0`; hata düzeltmeleri için `v0.7.1`, `v0.7.2`).
* **`v0.7.0` (Güncel Geliştirme Sürümü — Etiket / Tag):** Mobil İdare paneli şifre kapısı (`POST /api/admin/verify`), İdareden Öğretmen/İdare PIN değiştirme ve canlı senkronizasyon (`POST /api/settings/pins`), sunucu yeniden başlatmasında ve istemci açılışında kalıcı Kurum Adı koruması (`school_name_custom` self-healing + çoklu `load_config()`), `tahta-kilit_0.7.0_all.deb` paketi ve 13/13 geçen test paketi.
* **`v0.6.0` (Önceki Geliştirme Sürümü — Etiket / Tag) — Commit `44d158c`:** Yönetici Masaüstüne Dosya Gönderme (`POST /api/files/send`, `GET /api/files/download/{file_id}`, `FileDownloadThread`, Türkçe `~/Masaüstü` desteği, çakışmasız kayıt ve opsiyonel otomatik açma), `tahta-kilit_0.6.0_all.deb` paketi ve 11/11 geçen test paketi.
* **`v0.5.0` (Önceki Geliştirme Sürümü — Etiket / Tag) — Commit `451ac31`:** Akıllı `🔴 Canlı İzle` (`720px`, Smart Diff, 3 dk kota koruması), çoklu `📺 Önizleme Duvarı` (`POST /api/boards/thumbnails`, `320px`), tıklanabilir bağlantılı duyurular ve masaüstü sabit kilit üstü kart (`DesktopAnnouncementWidget`), 1B alt çekmeceli 4 satırlık öğretmen ekranı, `tahta-kilit_0.5.0_all.deb` paketi ve 10/10 geçen test paketi.
* **`v0.4.0` (Önceki Geliştirme Sürümü — Etiket / Tag):** Sürüm numarası `0.x` serisine geçirildi; Merkezi Uzaktan Güncelleme (`/api/bulk/update`, `/api/board/update`), mobil panelde sürüm rozeti ve canlı güncelleme yüzdesi, kilit ekranında `UpdateProgressOverlayWidget` ve masaüstünde `DesktopUpdateBanner`, açılışta ve 30 dakikada bir otomatik arka plan sürüm kontrolü, `tahta-kilit_0.4.0_all.deb` paketi ve 9/9 geçen test paketi.
* **`v1.3.1` (Önceki Etiket / Tag) — Commit `3e4e367`:** Fiziksel MAC + DMI donanım parmak izi ile Klon İmaj Koruması (Anti-Cloning), `etap-57435795` kara liste temizliği, Ayarlar ekranında `"🔄 Kimliği Yenile"`, canlı ekran görüntüsü (`v1.3.0`), toplu müdür yönetimi (`v1.2.0`–`v1.3.0`) ve 8/8 geçen test paketi.
* **`v1.0.0-stable` (Etiket / Tag) & `stable-v1.0` (Dal / Branch):** Commit `ab744e0` — Kiosk güvenliği (`BypassWindowManagerHint`), dahili katmanlar (Ayarlar, Yönetici Çıkışı, Duyuru), fiziksel + dokunmatik klavye desteği, masaüstü açıkken müdür duyuru penceresi ve iOS/Android PWA mobil arayüzünün tam çalışır, test edilmiş ilk kararlı sürümü.
* **Yerel Yedek Arşivi:** `backups/etap-smart-lock-v1.0.0-stable.zip`
* **İlk Kararlı Sürüme Geri Dönme Komutu:** `git checkout v1.0.0-stable` veya `git reset --hard v1.0.0-stable`
