import os

# Ortak Öğretmen PIN Kodu (Varsayılan: 1234 - Değiştirilebilir)
TEACHER_PIN = os.getenv("TEACHER_PIN", "1234")

# Müdür / İdare Giriş PIN Kodu (Varsayılan: 9999 - Değiştirilebilir)
ADMIN_PIN = os.getenv("ADMIN_PIN", "9999")

# QR Kod Güvenlik Gizli Anahtarı
SECRET_SALT = os.getenv("SECRET_SALT", "etap-super-secret-salt-2026")

# Dinamik QR Kod geçerlilik süresi (Saniye)
QR_VALIDITY_SECONDS = int(os.getenv("QR_VALIDITY_SECONDS", "45"))

# Merkezi Okul / Kurum Adı (İsteğe bağlı ortam değişkeni sabitlemesi)
SCHOOL_NAME = os.getenv("SCHOOL_NAME", "").strip()

# Akıllı Tahta WebSocket Kimlik Doğrulama Anahtarı (İsteğe bağlı — doluysa tahtalarda aynı değer gerekir)
BOARD_API_KEY = os.getenv("BOARD_API_KEY", "").strip()

# İzin Verilen CORS Kökenleri (Virgülle ayrılmış URL'ler veya '*')
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").strip()
