# ETAP Akıllı Kilit & Mobil Yönetim Sistemi — Proje Hafızası

Bu dosya, projenin bağlamını ve alınan mimari kararları yeni sohbet oturumlarına aktarmak için oluşturulmuştur.

## 📌 Proje Özeti
Pardus ETAP yüklü akıllı tahtalar için geliştirilen hibrit kilit ve anons sistemi:
1. **Online Mod (Normal):** Telefon 4.5G ile Render'daki Docker sunucusuna bağlanır, QR okutulunca tahta dokunulmadan otomatik açılır.
2. **Offline Mod (Yedek/Acil):** İnternet kesilirse tahtadaki dokunmatik ekrana ortak Öğretmen PIN kodu (`1234`) veya 30 saniyelik dinamik TOTP kodu girilerek açılır.
3. **Müdür Anons Sistemi:** İdareden gelen acil duyurular tahtanın en üstünde **mavi ışıklı kayan bant (LED Ticker)** olarak akar.
4. **Sınıf Tanımlama:** Tahtadaki ayarlar butonundan yetkili şifresiyle sınıf adı (Örn: `9-A`) kolayca değiştirilebilir.

## 📂 Dosya Yapısı
* `server/`: FastAPI + WebSockets sunucusu, Dockerfile ve `static/` altında mobil telefon arayüzü (PWA/QR okuyucu, manifest.json, sw.js, mobil ikonlar).
* `client-tahta/`: PyQt6 tam ekran kiosk kilit ekranı (`kilit_ekrani.py`), ayarlar (`config.ini`) ve Pardus kurulum betiği (`kur_pardus.sh`).
* `docker-compose.yml`: Yerel Docker testi için.
* `render.yaml`: Render.com ücretsiz bulut dağıtımı için.
* `KULLANIM_KILAVUZU.md`: Adım adım test, kullanım ve iOS/Android PWA mobil kurulum kılavuzu.
* `MEB_VE_RENDER_NOTLARI.md`: Render 15 dk uyku/kota optimizasyonu (cron-job.org) ve MEB Fatih ağı SSL/filtre rehberi.

## 🏷️ Versiyon Takibi & Kararlı Sürümler (Git)
* **`v1.0.0-stable` (Etiket / Tag) & `stable-v1.0` (Dal / Branch):** Commit `ab744e0` — Kiosk güvenliği (`BypassWindowManagerHint`), dahili katmanlar (Ayarlar, Yönetici Çıkışı, Duyuru), fiziksel + dokunmatik klavye desteği, masaüstü açıkken müdür duyuru penceresi ve iOS/Android PWA mobil arayüzünün tam çalışır, test edilmiş ilk kararlı sürümü.
* **Yerel Yedek Arşivi:** `backups/etap-smart-lock-v1.0.0-stable.zip`
* **Kararlı Sürüme Geri Dönme Komutu:** `git checkout v1.0.0-stable` veya `git reset --hard v1.0.0-stable`
