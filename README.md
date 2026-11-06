# ETAP Akıllı Kilit & Mobil Kontrol Sistemi (ETAP Smart Lock)

Pardus ETAP (Etkileşimli Tahta Arayüz Projesi) yüklü akıllı tahtalar için uzaktan ve akıllı telefon üzerinden kontrol edilebilen kilit sistemi.

## 🏗️ Sistem Mimarisi

```
 ┌──────────────────────────┐               ┌──────────────────────────┐
 │    Akıllı Telefon        │               │   Pardus ETAP Tahta      │
 │ (Öğretmen Web Arayüzü/PWA│               │  (Python/PyQt Kilit UI)  │
 └────────────┬─────────────┘               └────────────▲─────────────┘
              │                                          │
              │  HTTPS / QR Okuma                        │  WebSocket / MQTT
              ▼                                          │  (Anlık Kilit Açma)
 ┌───────────────────────────────────────────────────────┴─────────────┐
 │                     DOCKER BACKEND SERVİSİ                          │
 │  - FastAPI / WebSocket Sunucusu                                      │
 │  - Yetkilendirme & Token Yönetimi (Dinamik QR Kod)                  │
 │  - Redis / SQLite Veritabanı                                        │
 └─────────────────────────────────────────────────────────────────────┘
```

## 🚀 Temel Özellikler
1. **Dinamik QR Kod ile Kilit Açma:** Tahta ekranında periyodik olarak değişen güvenli QR kod.
2. **Mobil Kontrol Paneli:** Öğretmenin telefonundan tek tıkla tahtayı kilitleme / açma, ders süresi sayacı, acil durum kilidi.
3. **Pardus ETAP Uyumluluğu:** Debian/Ubuntu tabanlı Linux sistem servisi olarak arka planda stabil çalışma.
4. **Docker Desteği:** Sunucu katmanının tek komutla (`docker compose up`) her yerde çalıştırılabilmesi.
