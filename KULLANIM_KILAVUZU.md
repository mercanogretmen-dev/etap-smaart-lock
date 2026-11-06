# 📖 ETAP Akıllı Kilit & Mobil Yönetim — Hızlı Başlangıç Kılavuzu

Bu proje, Pardus ETAP akıllı tahtalar için internet varken cep telefonuyla tek tıkla açılan, internet kesildiğinde ise dokunmatik PIN ile kapıda bırakmayan hibrit bir kilit sistemidir.

---

## 🚀 1. Sunucuyu Kendi Bilgisayarınızda Çalıştırma (Docker)

Bilgisayarınızda projenin olduğu klasöre gelin (`etap-smart-lock`) ve terminalde şu komutu çalıştırın:

```bash
docker compose up -d --build
```

* Sunucunuz birkaç saniye içinde ayağa kalkacaktır.
* Tarayıcınızdan **`http://localhost:8000`** adresine gidin.
* Karşınıza mobil öğretmen arayüzü gelecektir!

---

## ☁️ 2. Sunucuyu İnternete (Render.com) Ücretsiz Yükleme

Telefonunuz 4.5G ile her yerden tahtayı açabilsin diye sunucuyu Render.com'a ücretsiz yükleyebilirsiniz:

1. Proje klasörünü bir GitHub deponuza (GitHub Repository) yükleyin.
2. [Render.com](https://render.com)'a ücretsiz üye olup **"New > Web Service"** seçin.
3. GitHub deponuzu seçin, Render projenin içindeki `render.yaml` ve `server/Dockerfile`'ı otomatik tanıyacaktır.
4. **Deploy** butonuna basın. Birkaç dakika sonra size `https://etap-smartlock-xyz.onrender.com` gibi ücretsiz bir web adresi verecektir.
5. Öğretmenler telefonlarından doğrudan bu adrese girip tahtaları kontrol edebilir!

---

## 🖥️ 3. Pardus ETAP Akıllı Tahtaya Kurulum

1. `client-tahta` klasörünü bir USB bellekle Pardus ETAP akıllı tahtaya kopyalayın (Örn: Masaüstüne).
2. `config.ini` dosyasını açıp sunucu adresinizi yazın:
   ```ini
   sinif_adi = 9-A
   sunucu_ws_url = wss://etap-smartlock-xyz.onrender.com/ws/board/
   ogretmen_pin = 1234
   ```
3. Uçbirimi (Terminal) açıp klasöre girin ve kurulumu çalıştırın:
   ```bash
   sudo bash kur_pardus.sh
   ```
4. Kurulum bittiğinde tahtayı yeniden başlatın; kilit ekranı otomatik olarak tam ekran başlayacaktır.

---

## 📱 4. Günlük Kullanım Senaryoları

* **İnternet Varken (Normal Ders Başlangıcı):**
  * Öğretmen sınıfa girer, telefonundan web adresini açıp tahtadaki QR kodu kameraya tutar.
  * Tahta **dokunmaya bile gerek kalmadan 1 saniyede otomatik açılır**.
* **İnternet Yokken (Yedek Acil Durum):**
  * Tahta ekranındaki dokunmatik tuş takımına ortak öğretmen PIN'ini (`1234`) veya telefonun "Çevrimdışı PIN" sekmesindeki 4 haneli dinamik kodu girip **🔓** butonuna basarak açar.
* **Müdür Bey Duyuru Göndermek İstediğinde:**
  * Telefonundan **"📢 Müdür / İdare"** sekmesine geçer.
  * İdare kodunu (`9999`) ve duyuru metnini yazıp gönderir.
  * Açık olan tüm tahtaların en üstünde mavi ışıklı kayan bant duyurusu akar.
