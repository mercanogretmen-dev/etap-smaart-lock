# 🛡️ TAHTA KİLİT — Kurulum, Güvenlik, Güncelleme ve Kaldırma Kılavuzu

Bu kılavuz, uygulamanın dosya yöneticisinde (Ev Dizini / `etapadmin`) açık duran bir `.py` betiği olmaktan çıkarılıp; **Pardus ETAP ve Windows üzerinde profesyonel, korumalı, tek tıkla güncellenebilen ve istendiğinde tek komutla tamamen kaldırılabilen bir sistem uygulaması** olarak nasıl yönetileceğini anlatır.

---

## 🔒 1. Güvenlik Sorunu ve Çözümü

### ❓ Neden `.py` Dosyası Ev Dizininde Görünüyordu?
Pardus terminalinde `git clone` komutu `/home/etapadmin` altında çalıştırıldığında, git deposu doğrudan kullanıcının kişisel klasörüne (`Ev Dizini`) iner. Bu durum hem dosya yöneticisinde kalabalık yaratır hem de öğrencilerin `.py` dosyasını açıp kodları/şifreleri kurcalamasına zemin hazırlar.

### 🛡️ Nasıl Koruma Altına Alındı?
1. **Korumalı Sistem Dizini (`/opt/etap-smartlock`):** Program artık sistem seviyesindeki `/opt` dizinine kurulur ve sahibi `root` yapılır (`chmod 755`). Normal kullanıcılar ve öğrenciler bu klasördeki hiçbir dosyayı **değiştiremez veya silemez**.
2. **Python Baytkod Derleme (`.pyc`):** Kurulum sırasında Python dosyaları makine koduna (`.pyc`) derlenir; böylece metin editörlerinde doğrudan okunamaz.
3. **Ev Dizini Temizliği:** Kurulum betiği, açıkta duran depoyu otomatik olarak gizli klasöre (`.etap-smartlock`) çevirir. Linux dosya yöneticisinde gizli klasörler görünmez; **Ev Dizini tamamen temiz kalır**.

---

## 🐧 2. PARDUS ETAP İÇİN KURULUM & GÜNCELLEME

### 🚀 Yöntem A: Tek Komutla Otomatik Kurulum (Önerilen)
Pardus terminalini açın ve şu komutu verin:

```bash
cd ~/etap-smaart-lock && sudo bash kur_pardus.sh
```

**Bu betik neleri otomatik yapar?**
- Gerekli tüm sistem kütüphanelerini (`PyQt6`, `qrcode`, `pil`, `websockets`) yükler.
- Programı `/opt/etap-smartlock` altına taşır ve izinleri `root` olarak kilitler.
- `/usr/local/bin/tahta-kilit` sistem komutunu oluşturur.
- Tahta açıldığında veya yeniden başlatıldığında otomatik açılması için `autostart` kaydını yapar.
- Pardus Başlat / Uygulamalar menüsüne logosuyla birlikte **Tahta Kilit** kısayolunu ekler.

---

### 📦 Yöntem B: Çift Tıklamayla Kurulan Pardus Paketi (`.deb`) Üretme
Eğer birden fazla tahtaya USB ile kurulum yapmak isterseniz, tek satırla standart Debian paketi oluşturabilirsiniz:

```bash
bash build_deb.sh
```
- Bu komut `tahta-kilit_1.1.0_all.deb` dosyasını üretir.
- Üretilen `.deb` paketini USB belleğe atıp herhangi bir tahtada **çift tıklayarak (Pardus Paket Kurucu ile)** tıpkı Chrome veya LibreOffice kurar gibi sisteme yükleyebilirsiniz.

---

### 🔄 Pardus'ta Değişiklikleri Güncelleme (2 Farklı Yol)

#### 1. Tahtanın Ekranından (Tek Tıkla - Terminale Girmeden!)
1. Kilit ekranında sağ üstteki **⚙️ Ayarlar** butonuna dokunun.
2. Öğretmen/Yönetici şifresini girin.
3. Açılan ayarlar panelinde mavi renkli **`🔄 Güncelle (GitHub)`** butonuna basın.
4. Tahta arka planda en güncel kodları çeker, sisteme kurar ve kilit ekranını yeni sürümle yeniden başlatır!

#### 2. Terminalden:
```bash
tahta-kilit-guncelle
```
*(veya `cd ~/etap-smaart-lock && bash guncelle.sh`)*

---

## 🪟 3. WINDOWS İÇİN KURULUM & GÜNCELLEME

Windows bilgisayarlar veya öğretmen laptopları için:

### 🚀 Yöntem A: Tek Tıkla Windows Kurulumu (`kur_windows.bat`)
1. Klasördeki **`kur_windows.bat`** dosyasına çift tıklayın.
2. Program otomatik olarak kütüphaneleri kurar, `%LOCALAPPDATA%\TahtaKilit` dizinine yerleştirir, Masaüstüne ve Windows Başlangıç (`Startup`) klasörüne kısayol ekler.

### 🔨 Yöntem B: Bağımsız `.EXE` Derleme (`derle_windows.bat`)
1. **`derle_windows.bat`** dosyasına çift tıklayın.
2. PyInstaller aracı `dist\TahtaKilit.exe` dosyasını üretir (56 MB, tüm Python ve Qt kütüphaneleri içine gömülüdür).
3. Bu `.exe` dosyasını herhangi bir Windows bilgisayara kopyalayıp doğrudan çalıştırabilirsiniz; Python kurulu olmasına bile gerek yoktur!

### 🔄 Windows'ta Güncelleme
- Klasördeki **`guncelle.bat`** dosyasına çift tıklayın veya kilit ekranındaki **⚙️ Ayarlar** panelindeki **`🔄 Güncelle (GitHub)`** butonuna basın.

---

## 🗑️ 4. SİSTEMDEN TAMAMEN KALDIRMA (UNINSTALL)

Eğer programı bilgisayardan veya akıllı tahtadan tamamen kaldırmak isterseniz:

### 🐧 Pardus ETAP'tan Tamamen Kaldırmak İçin:

Bunu **Pardus Uçbirim (Terminal)** penceresine yazacaksınız. 3 farklı ve kolay yoldan birini seçebilirsiniz:

#### 🌟 1. En Pratik Yol (Her Yerden Çalışan Tek Komut):
Eğer program daha önce kurulduysa, herhangi bir klasör aramanıza gerek yoktur.
1. Klavyeden **`Ctrl + Alt + T`** tuşlarına basarak veya sol alttaki Pardus simgesinden **"Uçbirim"**i (Terminal) açın.
2. Açılan siyah ekrana şu komutu yazıp `Enter`'a basın:
   ```bash
   sudo tahta-kilit-kaldir
   ```
3. Yönetici şifrenizi (`etapadmin`) girin. Sistem saniyeler içinde tamamen temizlenir.

---

#### 📁 2. Proje Klasöründen Kaldırma:
Uçbirim (Terminal) ekranını açın ve şu iki satırı yazıp `Enter`'a basın:
```bash
cd ~/etap-smaart-lock
sudo bash kaldir_pardus.sh
```

---

#### 🖱️ 3. Dosya Yöneticisinden (Fare ile):
1. Pardus dosya yöneticisinde `etap-smaart-lock` klasörünün içine girin.
2. Boş bir alana **sağ tıklayın** ve **"Burada Uçbirim Aç"** seçeneğini tıklayın.
3. Açılan küçük siyah pencereye şunu yazıp `Enter`'a basın:
   ```bash
   sudo bash kaldir_pardus.sh
   ```

---

**Bu kaldırma betiği neleri temizler?**
1. Çalışan kilit ekranını sonlandırır.
2. Açılışta otomatik başlama kayıtlarını (`/etc/xdg/autostart/tahta-kilit.desktop`) siler.
3. Pardus Başlat Menüsündeki kısayolu (`/usr/share/applications/tahta-kilit.desktop`) kaldırır.
4. Sistem komutlarını (`/usr/local/bin/tahta-kilit*`) temizler.
5. `/opt/etap-smartlock` kurulum dizinini tamamen siler.
6. Eğer `.deb` paketi olarak kurulduysa `dpkg --purge` ile paket kaydını da temizler.
7. Yapılandırma ve önbellek dosyalarını (`/etc/etap-smartlock`, `~/.config/etap-smartlock`) sıfırlar.

*(Kaynak kod klasörünü de silmek isterseniz: `rm -rf ~/etap-smaart-lock ~/.etap-smartlock`)*

---

### 🪟 Windows'tan Tamamen Kaldırmak İçin:
- Proje klasöründeki **`kaldir_windows.bat`** dosyasına çift tıklayın.
- Çalışan süreci kapatır, Masaüstü ve Başlangıç kısayollarını siler, `%LOCALAPPDATA%\TahtaKilit` ve tüm ayar dosyalarını tertemiz kaldırır.
