# 📡 Render Bulut Barındırma & MEB Fatih Ağı Operasyon Rehberi

Bu belge; Render üzerindeki sunucunun çalışma saatlerini optimize etmek (15 dakika uyku modunu ve 750 saatlik kotayı yönetmek) ile MEB Fatih internet hattındaki olası kısıtlamaları aşmak için hazırlanan başvuru kılavuzudur.

---

## 1. Render Uyku Modu (Cold Start) & 750 Saat Kota Yönetimi

### 📌 Problem Tanımı
* **Render Ücretsiz Plan Kuralı:** Sunucuya 15 dakika boyunca HTTP isteği gelmezse sunucu otomatik olarak uykuya geçer (*Spin Down*).
* **Cold Start (Soğuk Başlangıç):** Uyku modundaki sunucuya ilk istek geldiğinde uyanması **30 ila 50 saniye** sürer. Sınıfta ders başında öğretmenin beklemesi istenmeyen bir durumdur.
* **Kota:** Ücretsiz planda her ay hesap başına **750 saat** ücretsiz çalışma süresi verilir. (Bir ay 720 saattir, yani 7/24 çalışsa bile tek servis kotayı aşmaz; fakat kaynakları tasarruflu kullanmak ve 15 dk uykusunu engellemek gerekir).

### 💡 Çözüm: cron-job.org ile Zaman Ayarlı Canlı Tutma (07:50 - 18:00)

Sunucuyu sadece okul saatlerinde uyanık tutarak gecikmeyi sıfırlayabilir ve aylık kotanın sadece üçte birini harcayabilirsiniz.

#### Adım Adım Kurulum:
1. [cron-job.org](https://cron-job.org/en/) sitesine gidip ücretsiz bir hesap açın.
2. **"Create Cronjob"** butonuna tıklayın ve şu ayarları girin:
   * **Title:** `ETAP Kilit Uyanık Tutucu`
   * **URL:** `https://etap-smaart-lock.onrender.com/api/boards`
   * **Schedule:**
     * **Execution interval:** Her 10 dakikada bir (*Every 10 minutes*)
     * **Timezone:** `Europe/Istanbul` (Türkiye Saati)
     * **Hours:** `07:50` ile `18:00` arası
     * **Days of week:** Pazartesi, Salı, Çarşamba, Perşembe, Cuma (Hafta sonu kapalı)
3. **Kayıt:** Ayarları kaydedip görevi aktif edin.

#### Kazanımlar:
* 🌅 Sabah 07:50'de giden ilk ping ile sunucu dersler başlamadan önce uyanır.
* ⚡ 08:00 - 18:00 saatleri arasında her 10 dakikada bir ping gittiği için sunucu **asla uykuya geçmez**, kilit açma emirleri anında (0.1 sn) çalışır.
* 🌙 Saat 18:00'den sonra pingler durur ve Render 18:15'te uykuya dalar.
* 📉 **Kota Tüketimi:** Günde 10.5 saat x 22 iş günü = **Ayda ~230 saat** (750 saatlik kotanın sadece %30'u kullanılır).

---

## 2. MEB İnternet Hattı (Fatih Ağı) & Güvenlik Duvarı Durumu

Akıllı tahtalar MEB Fatih altyapısına bağlı olduğunda iki teknik durumla karşılaşılabilir:

### ⚠️ Durum A: MEB Filtresinin onrender.com Alan Adını Engellemesi
MEB Fortinet güvenlik duvarı, `*.onrender.com` gibi ücretsiz bulut uzantılarını *"Kategorize Edilmemiş / Dinamik Barındırma"* gerekçesiyle bazı il/okullarda engelleyebilir.

* **Nasıl Test Edilir?**
  Tahtanın web tarayıcısından `https://etap-smaart-lock.onrender.com` adresini açmayı deneyin. Sayfa açılıyorsa engel yoktur.
* **Eğer Engelliyse Ne Yapılmalı?**
  1. **Özel Alan Adı (Tavsiye Edilen):** Render panosundan projeye bir özel alan adı (Örn: Cloudflare arkasında `kilit.okulunuz.com` veya ucuz bir `.com/.xyz` alan adı) bağlanabilir. MEB filtreleri özel alan adlarını doğrudan engellemez.
  2. **MEB İzin Talebi:** İlçe Fatih Projesi Koordinatörüne başvurularak ilgili alan adının okul için güvenli listeye (beyaz liste) eklenmesi talep edilebilir.

---

### ⚠️ Durum B: MEB Kök Sertifikası (fatihca) ve SSL İncelemesi
MEB ağı, trafiği denetlemek için derin paket incelemesi (Deep Packet Inspection) yapar ve kendi kök sertifikasını (`fatihca.crt`) kullanır.
Python kütüphaneleri varsayılan olarak bu sertifikayı tanımadığı için tahta WebSocket'e bağlanırken şu hatayı verebilir:
`SSL: CERTIFICATE_VERIFY_FAILED: self-signed certificate in certificate chain`

* **Kod Düzeyinde Çözüm:**
  `client-tahta/kilit_ekrani.py` içinde WebSocket bağlantısı başlatılırken MEB ortamı için esnek bir SSL Context (`ssl.create_default_context` ve gerektiğinde `ssl.CERT_NONE` yedeği) tanımlandığında bu engel tamamen aşılır.

---

## 3. Uzun Vadeli Alternatif: Okul İçi Yerel Sunucu (Local Server / Raspberry Pi)

Eğer tamamen MEB hattından ve bulut kotalarından bağımsız bir sistem istenirse:
* Okul idaresindeki bir bilgisayarda veya okul panosuna yerleştirilecek bir **Raspberry Pi** üzerinde `docker-compose up` ile sunucu yerel ağda (LAN) çalıştırılabilir.
* Öğretmen telefonları okul Wi-Fi ağına bağlandığında 0 internet kotası ve 0 gecikmeyle çalışır.
* 4.5G ile dışarıdan erişim için ise ücretsiz **Cloudflare Tunnel (cloudflared)** kullanılabilir.
