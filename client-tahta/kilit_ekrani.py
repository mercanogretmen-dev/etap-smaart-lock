#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETAP Akıllı Kilit & Mobil Yönetim Sistemi — Pardus ETAP Kilit İstemcisi
Pardus ETAP üzerinde tam ekran kiosk kilidi, dinamik QR kod, dokunmatik PIN
ve mavi ışıklı müdür duyuru bandını yönetir.
"""

import sys
import os
import time
import json
import configparser
import asyncio
from datetime import datetime
import qrcode
from PIL import Image

try:
    import websockets
except ImportError:
    websockets = None

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QTime, QDate, QProcess, QEvent
from PyQt6.QtGui import QFont, QPixmap, QImage, QKeyEvent, QColor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QGridLayout, QLineEdit, QDialog, QInputDialog,
    QMessageBox, QFrame, QGraphicsDropShadowEffect
)

SYSTEM_CONFIG_DIR = "/etc/etap-smartlock"
SYSTEM_CONFIG_PATH = os.path.join(SYSTEM_CONFIG_DIR, "config.ini")
USER_CONFIG_DIR = os.path.expanduser("~/.config/etap-smartlock")
USER_CONFIG_PATH = os.path.join(USER_CONFIG_DIR, "config.ini")
LOCAL_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")

def get_config_search_paths():
    """Tüm olası konfigürasyon yollarını öncelik sırasıyla döner."""
    return [
        USER_CONFIG_PATH,
        SYSTEM_CONFIG_PATH,
        LOCAL_CONFIG_PATH
    ]

def load_config():
    config = configparser.ConfigParser()
    loaded_from = None

    # Mevcut config dosyalarını bul ve en son değiştirileni (en günceli) yükle
    existing_paths = [p for p in get_config_search_paths() if os.path.exists(p)]
    if existing_paths:
        existing_paths.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        for p in existing_paths:
            try:
                config.read(p, encoding="utf-8")
                loaded_from = p
                print(f"📖 Config en güncel dosyadan yüklendi: {p}")
                break
            except Exception as e:
                print(f"Config okuma hatası [{p}]: {e}")

    if "GENEL" not in config:
        config["GENEL"] = {}

    defaults = {
        "sinif_adi": "9-A",
        "sunucu_ws_url": "wss://etap-smaart-lock.onrender.com/ws/board/",
        "ogretmen_pin": "1234",
        "yonetici_sifre": "admin123",
        "cihaz_id": ""
    }
    for k, v in defaults.items():
        if k not in config["GENEL"] or not str(config["GENEL"][k]).strip():
            config["GENEL"][k] = v

    return config

def get_device_id(config):
    """Her tahta için benzersiz ve kalıcı donanım/cihaz kimliğini döner."""
    dev_id = config.get("GENEL", "cihaz_id", fallback="").strip()
    if dev_id:
        return dev_id

    # 1. Linux Pardus machine-id kontrolü
    for mid_file in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
        if os.path.exists(mid_file):
            try:
                with open(mid_file, "r") as f:
                    content = f.read().strip()
                    if content:
                        dev_id = f"etap-{content[:8]}"
                        break
            except Exception:
                pass

    # 2. Bulunamazsa benzersiz UUID üret
    if not dev_id:
        import uuid
        dev_id = f"etap-{uuid.uuid4().hex[:8]}"

    config.set("GENEL", "cihaz_id", dev_id)
    save_config(config)
    return dev_id

def save_config(config):
    """
    Ayarları kalıcı olarak TÜM erişilebilir konfigürasyon yollarına (/etc, ~/.config, yerel) kaydeder.
    Böylece tahta yeniden başlatılsa bile yeni isim asla kaybolmaz.
    """
    saved_any = False
    target_paths = [
        SYSTEM_CONFIG_PATH,
        USER_CONFIG_PATH,
        LOCAL_CONFIG_PATH
    ]

    for p in target_paths:
        try:
            d = os.path.dirname(p)
            if d and not os.path.exists(d):
                os.makedirs(d, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                config.write(f)
            # Linux'ta diğer kullanıcıların (ogretmen, etapadmin) da okuyup yazabilmesi için izin ver
            try:
                os.chmod(p, 0o666)
            except Exception:
                pass
            saved_any = True
            print(f"💾 Config kaydedildi: {p}")
        except Exception as e:
            # İzin yetmeyen dizinleri geç
            pass

    return saved_any


# -------------------------------------------------------------
# 📡 Arka Plan WebSocket İstemci İş Parçacığı (Thread)
# -------------------------------------------------------------
class WebSocketClientThread(QThread):
    signal_status = pyqtSignal(bool)           # True = Çevrimiçi, False = Çevrimdışı
    signal_command = pyqtSignal(dict)          # Sunucudan gelen kilit/duyuru komutları

    def __init__(self, ws_url: str, device_id: str, board_name: str):
        super().__init__()
        import urllib.parse
        self.raw_ws_url = ws_url.rstrip("/")
        self.device_id = device_id
        self.board_name = board_name
        self.running = True
        self.ws = None
        self.loop = None
        self._build_url()

    def _build_url(self):
        import urllib.parse
        encoded_name = urllib.parse.quote(self.board_name)
        self.ws_url = f"{self.raw_ws_url}/{self.device_id}?name={encoded_name}"

    def run(self):
        if not websockets:
            self.signal_status.emit(False)
            return

        asyncio.run(self.connect_loop())

    async def connect_loop(self):
        self.loop = asyncio.get_running_loop()
        while self.running:
            self._build_url()
            try:
                async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=10) as ws:
                    self.ws = ws
                    self.signal_status.emit(True)
                    while self.running:
                        try:
                            msg_text = await asyncio.wait_for(ws.recv(), timeout=1.0)
                            data = json.loads(msg_text)
                            self.signal_command.emit(data)
                        except asyncio.TimeoutError:
                            continue
                        except (websockets.ConnectionClosed, Exception):
                            break
                    self.ws = None
            except Exception:
                self.ws = None
                self.signal_status.emit(False)
                for _ in range(6):
                    if not self.running:
                        break
                    await asyncio.sleep(0.5)

    def send_name_update(self, new_name: str) -> bool:
        """Açık olan WebSocket bağlantısı üzerinden isim güncellemesi gönderir (bağlantı kopmaz)."""
        self.board_name = new_name
        self._build_url()
        if self.ws and self.loop and self.loop.is_running():
            try:
                payload = json.dumps({"action": "update_name", "name": new_name})
                asyncio.run_coroutine_threadsafe(self.ws.send(payload), self.loop)
                print(f"📤 WebSocket üzerinden anlık isim güncellemesi gönderildi: {new_name}")
                return True
            except Exception as e:
                print(f"İsim gönderme hatası: {e}")
        return False

    def stop(self):
        self.running = False
        if self.ws and self.loop and self.loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self.ws.close(), self.loop)
            except Exception:
                pass
        try:
            if self.isRunning():
                self.quit()
                self.wait(1500)
        except Exception:
            pass


# -------------------------------------------------------------
# 🔊 Sesli Uyarı ve Bildirim Zili
# -------------------------------------------------------------
def play_alert_sound():
    """Müdür duyurusu geldiğinde dikkat çeken hoş bir melodi çalar."""
    # 1. Windows platformu
    if sys.platform == "win32":
        try:
            import winsound
            winsound.Beep(784, 150)  # G5
            time.sleep(0.04)
            winsound.Beep(1046, 280) # C6
            return
        except Exception:
            pass

    # 2. Linux / Pardus ETAP üzerinde sistem seslerini dene
    for cmd in [
        "canberra-gtk-play -i message",
        "paplay /usr/share/sounds/freedesktop/stereo/complete.oga",
        "paplay /usr/share/sounds/freedesktop/stereo/bell.oga"
    ]:
        if os.system(f"{cmd} > /dev/null 2>&1") == 0:
            return

    # 3. Saf Python ile dahili 2 tonlu melodi üret ve aplay ile çal
    try:
        wav_path = "/tmp/etap_chime.wav"
        if not os.path.exists(wav_path):
            import wave, math, struct
            sr = 22050
            dur = 0.45
            with wave.open(wav_path, "w") as wf:
                wf.setparams((1, 2, sr, int(sr * dur), "NONE", "not compressed"))
                for i in range(int(sr * dur)):
                    t = float(i) / sr
                    freq = 659.25 if t < 0.18 else 880.0
                    decay = max(0.0, 1.0 - (t / dur))
                    val = int(math.sin(2.0 * math.pi * freq * t) * 16383 * decay)
                    wf.writeframes(struct.pack("<h", val))
        os.system(f"aplay -q {wav_path} > /dev/null 2>&1 &")
    except Exception:
        pass


# -------------------------------------------------------------
# 📢 Kilit Ekranı İçine Gömülü Duyuru Katmanı (In-Window Overlay)
# Bu katman yeni bir X11/OS penceresi açmadığı için Pardus tarafında
# alt görev çubuğunun (xfce4-panel) KESİNLİKLE ortaya çıkmamasını sağlar.
# -------------------------------------------------------------
class AnnouncementOverlayWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.duration_left = 45
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.init_ui()
        self.hide()

    def init_ui(self):
        # Yarı saydam koyu karartma arka planı (Backdrop)
        self.setStyleSheet("background: rgba(0, 0, 0, 0.82);")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(20, 20, 20, 20)

        self.frame = QFrame()
        self.frame.setFixedSize(700, 390)
        self.frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0f172a, stop:1 #1e293b);
                border: 2px solid #38bdf8;
                border-radius: 24px;
            }
        """)
        glow = QGraphicsDropShadowEffect(self.frame)
        glow.setBlurRadius(50)
        glow.setColor(QColor(56, 189, 248, 190))
        glow.setOffset(0, 4)
        self.frame.setGraphicsEffect(glow)

        frame_layout = QVBoxLayout(self.frame)
        frame_layout.setContentsMargins(35, 26, 35, 25)
        frame_layout.setSpacing(16)

        # Üst Başlık & Kapat Butonu
        header = QHBoxLayout()
        icon = QLabel("📢")
        icon.setFont(QFont("Segoe UI Emoji", 26))
        header.addWidget(icon)

        title = QLabel("MÜDÜR / İDARE DUYURUSU")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.ExtraBold))
        title.setStyleSheet("color: #38bdf8; letter-spacing: 1.5px;")
        header.addWidget(title)
        header.addStretch()

        btn_close_top = QPushButton("✕")
        btn_close_top.setFixedSize(36, 36)
        btn_close_top.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        btn_close_top.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 18px;
            }
            QPushButton:hover { background: #ef4444; color: white; border-color: #ef4444; }
        """)
        btn_close_top.clicked.connect(self.close_announcement)
        header.addWidget(btn_close_top)
        frame_layout.addLayout(header)

        # Mesaj Metni
        self.msg_label = QLabel("")
        self.msg_label.setFont(QFont("Segoe UI", 16, QFont.Weight.DemiBold))
        self.msg_label.setStyleSheet("""
            color: #ffffff;
            background: rgba(15, 23, 42, 0.7);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 16px;
            padding: 20px;
            line-height: 1.45;
        """)
        self.msg_label.setWordWrap(True)
        self.msg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(self.msg_label, 1)

        # Alt Çubuk (Geri Sayım & Kapat Butonu)
        bottom = QHBoxLayout()
        self.lbl_countdown = QLabel("⏱️ 45 saniye sonra kendiliğinden kapanır")
        self.lbl_countdown.setFont(QFont("Segoe UI", 11))
        self.lbl_countdown.setStyleSheet("color: #94a3b8;")
        bottom.addWidget(self.lbl_countdown)
        bottom.addStretch()

        btn_dismiss = QPushButton("Tamam / Kapat")
        btn_dismiss.setFixedSize(140, 42)
        btn_dismiss.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        btn_dismiss.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #0369a1);
                color: #ffffff;
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.2);
            }
            QPushButton:hover { background: #0284c7; }
            QPushButton:pressed { background: #075985; }
        """)
        btn_dismiss.clicked.connect(self.close_announcement)
        bottom.addWidget(btn_dismiss)
        frame_layout.addLayout(bottom)

        layout.addWidget(self.frame)

    def show_announcement(self, message: str, duration_sec: int = 45):
        self.msg_label.setText(message)
        self.duration_left = duration_sec
        self.lbl_countdown.setText(f"⏱️ {self.duration_left} saniye sonra kendiliğinden kapanır")
        if self.parent():
            self.setGeometry(0, 0, self.parent().width(), self.parent().height())
        self.show()
        self.raise_()
        self.timer.stop()
        self.timer.start(1000)

    def close_announcement(self):
        self.timer.stop()
        self.hide()

    def tick(self):
        self.duration_left -= 1
        if self.duration_left <= 0:
            self.close_announcement()
        else:
            self.lbl_countdown.setText(f"⏱️ {self.duration_left} saniye sonra kendiliğinden kapanır")


# -------------------------------------------------------------
# 📢 Masaüstü Açıkken Ortada Açılan Modern İdare Duyuru Kutusu (Tool Popup)
# -------------------------------------------------------------
class AnnouncementModalDialog(QDialog):
    def __init__(self, message: str, duration_sec: int = 45, parent=None):
        super().__init__(parent)
        self.setWindowTitle("İdare Duyurusu")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(680, 380)

        self.duration_left = duration_sec

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        self.frame = QFrame()
        self.frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0f172a, stop:1 #1e293b);
                border: 2px solid #38bdf8;
                border-radius: 24px;
            }
        """)
        glow = QGraphicsDropShadowEffect(self.frame)
        glow.setBlurRadius(50)
        glow.setColor(QColor(56, 189, 248, 190))
        glow.setOffset(0, 4)
        self.frame.setGraphicsEffect(glow)

        frame_layout = QVBoxLayout(self.frame)
        frame_layout.setContentsMargins(35, 26, 35, 25)
        frame_layout.setSpacing(16)

        # Üst Başlık & Kapat Butonu
        header = QHBoxLayout()
        icon = QLabel("📢")
        icon.setFont(QFont("Segoe UI Emoji", 26))
        header.addWidget(icon)

        title = QLabel("MÜDÜR / İDARE DUYURUSU")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.ExtraBold))
        title.setStyleSheet("color: #38bdf8; letter-spacing: 1.5px;")
        header.addWidget(title)
        header.addStretch()

        btn_close_top = QPushButton("✕")
        btn_close_top.setFixedSize(36, 36)
        btn_close_top.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        btn_close_top.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 18px;
            }
            QPushButton:hover { background: #ef4444; color: white; border-color: #ef4444; }
        """)
        btn_close_top.clicked.connect(self.accept)
        header.addWidget(btn_close_top)
        frame_layout.addLayout(header)

        # Mesaj Metni
        msg_label = QLabel(message)
        msg_label.setFont(QFont("Segoe UI", 16, QFont.Weight.DemiBold))
        msg_label.setStyleSheet("""
            color: #ffffff;
            background: rgba(15, 23, 42, 0.7);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 16px;
            padding: 20px;
            line-height: 1.45;
        """)
        msg_label.setWordWrap(True)
        msg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(msg_label, 1)

        # Alt Çubuk (Geri Sayım & Kapat Butonu)
        bottom = QHBoxLayout()
        self.lbl_countdown = QLabel(f"⏱️ {self.duration_left} saniye sonra kendiliğinden kapanır")
        self.lbl_countdown.setFont(QFont("Segoe UI", 11))
        self.lbl_countdown.setStyleSheet("color: #94a3b8;")
        bottom.addWidget(self.lbl_countdown)
        bottom.addStretch()

        btn_dismiss = QPushButton("Tamam / Kapat")
        btn_dismiss.setFixedSize(140, 42)
        btn_dismiss.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        btn_dismiss.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #0369a1);
                color: #ffffff;
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.2);
            }
            QPushButton:hover { background: #0284c7; }
            QPushButton:pressed { background: #075985; }
        """)
        btn_dismiss.clicked.connect(self.accept)
        bottom.addWidget(btn_dismiss)
        frame_layout.addLayout(bottom)

        layout.addWidget(self.frame)

        # Geri sayım zamanlayıcısı
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)

    def tick(self):
        self.duration_left -= 1
        if self.duration_left <= 0:
            self.timer.stop()
            self.accept()
        else:
            self.lbl_countdown.setText(f"⏱️ {self.duration_left} saniye sonra kendiliğinden kapanır")


# -------------------------------------------------------------
# 📢 Mavi Işıklı Kayan Bant Bileşeni (Müdür Duyurusu)
# -------------------------------------------------------------
class BlueBannerTicker(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(54)
        self.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:0.5 #0369a1, stop:1 #0284c7);
                border-bottom: 2px solid #38bdf8;
            }
        """)

        # Mavi neon ışıma efekti
        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(20)
        glow.setColor(QColor(56, 189, 248, 200))
        glow.setOffset(0, 2)
        self.setGraphicsEffect(glow)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)

        self.icon_label = QLabel("📢 İDARE DUYURUSU:")
        self.icon_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.icon_label.setStyleSheet("color: #fef08a; background: transparent;")
        layout.addWidget(self.icon_label)

        self.text_label = QLabel("")
        self.text_label.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.text_label.setStyleSheet("color: #ffffff; background: transparent;")
        layout.addWidget(self.text_label, 1)

        self.timer_close = QTimer(self)
        self.timer_close.timeout.connect(self.hide)

        self.hide()

    def show_message(self, message: str, duration_sec: int = 60):
        self.text_label.setText(message)
        self.show()
        self.timer_close.stop()
        self.timer_close.start(duration_sec * 1000)


# -------------------------------------------------------------
# ⚙️ Yetkili Ayarlar İletişim Kutusu
# -------------------------------------------------------------
class SettingsDialog(QDialog):
    def __init__(self, current_board: str, current_url: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sistem Ayarları")
        self.setFixedSize(420, 320)
        self.setStyleSheet("background-color: #1e293b; color: #f8fafc;")

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        lbl = QLabel("Akıllı Tahta Sistem Ayarları")
        lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        lbl.setStyleSheet("color: #38bdf8;")
        layout.addWidget(lbl)

        layout.addWidget(QLabel("Sınıf / Tahta Adı:"))
        self.input_board = QLineEdit(current_board)
        self.input_board.setStyleSheet("padding: 8px; border-radius: 6px; background: #0f172a; color: white;")
        layout.addWidget(self.input_board)

        layout.addWidget(QLabel("Merkezi Sunucu WebSocket Adresi:"))
        self.input_url = QLineEdit(current_url)
        self.input_url.setStyleSheet("padding: 8px; border-radius: 6px; background: #0f172a; color: white;")
        layout.addWidget(self.input_url)

        btn_box = QHBoxLayout()
        btn_save = QPushButton("💾 Kaydet ve Uygula")
        btn_save.setStyleSheet("background: #10b981; color: white; padding: 10px; font-weight: bold; border-radius: 6px;")
        btn_save.clicked.connect(self.accept)

        btn_cancel = QPushButton("İptal")
        btn_cancel.setStyleSheet("background: #475569; color: white; padding: 10px; border-radius: 6px;")
        btn_cancel.clicked.connect(self.reject)

        btn_box.addWidget(btn_save)
        btn_box.addWidget(btn_cancel)
        layout.addLayout(btn_box)


# -------------------------------------------------------------
# 🔒 Ana Kilit Ekranı Penceresi (Kiosk / Fullscreen)
# -------------------------------------------------------------
class LockScreenWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.cihaz_id = get_device_id(self.cfg)
        self.sinif_adi = self.cfg.get("GENEL", "sinif_adi", fallback="9-A")
        self.sunucu_url = self.cfg.get("GENEL", "sunucu_ws_url", fallback="wss://etap-smaart-lock.onrender.com/ws/board/")
        self.ogretmen_pin = self.cfg.get("GENEL", "ogretmen_pin", fallback="1234")
        self.yonetici_sifre = self.cfg.get("GENEL", "yonetici_sifre", fallback="admin123")

        self.entered_pin = ""
        self.is_locked = True
        self.announcement_overlay = None

        self.init_ui()
        self.init_network()
        self.setup_kiosk_security()

    def init_ui(self):
        # Tam Ekran Kiosk Pencere Özellikleri
        # BypassWindowManagerHint: X11 pencere yöneticisini (XFCE xfwm4) atlar,
        # böylece Windows+D masaüstünü göster kısayolu kilit ekranını ASLA minimize edemez!
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.BypassWindowManagerHint
        )
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.setStyleSheet("background-color: #0b1120; color: #f8fafc;")

        # Ana Düzen
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. En Üst: Mavi Işıklı Duyuru Bandı
        self.banner = BlueBannerTicker(self)
        main_layout.addWidget(self.banner)

        # 2. Üst Bar: Sınıf Adı, Bağlantı Rozeti ve Ayarlar
        top_bar = QWidget()
        top_bar.setFixedHeight(70)
        top_bar.setStyleSheet("background-color: #0f172a; border-bottom: 1px solid #1e293b;")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(30, 0, 30, 0)

        self.lbl_class = QLabel(f"🖥️ {self.sinif_adi}")
        self.lbl_class.setFont(QFont("Segoe UI", 16, QFont.Weight.ExtraBold))
        self.lbl_class.setStyleSheet("color: #38bdf8; background: rgba(56, 189, 248, 0.12); padding: 6px 18px; border-radius: 12px; border: 1px solid rgba(56, 189, 248, 0.25);")
        top_layout.addWidget(self.lbl_class)

        lbl_dev = QLabel(f"🆔 {self.cihaz_id}")
        lbl_dev.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl_dev.setStyleSheet("color: #64748b; background: rgba(255, 255, 255, 0.04); padding: 6px 12px; border-radius: 8px; border: 1px solid rgba(255, 255, 255, 0.06);")
        top_layout.addWidget(lbl_dev)

        top_layout.addStretch()

        self.lbl_status = QLabel("● Çevrimdışı (PIN Modu)")
        self.lbl_status.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.lbl_status.setStyleSheet("color: #f87171; background: rgba(239, 68, 68, 0.1); padding: 6px 14px; border-radius: 999px;")
        top_layout.addWidget(self.lbl_status)

        btn_settings = QPushButton("⚙️")
        btn_settings.setFixedSize(40, 40)
        btn_settings.setFont(QFont("Segoe UI", 13))
        btn_settings.setStyleSheet("background: #1e293b; color: white; border-radius: 8px; border: 1px solid #334155;")
        btn_settings.clicked.connect(self.open_settings)
        top_layout.addWidget(btn_settings)

        main_layout.addWidget(top_bar)

        # 3. Orta Gövde: Sol (QR Kod & Saat) | Sağ (Dokunmatik PIN Numpad)
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(60, 40, 60, 40)
        body_layout.setSpacing(60)

        # --- SOL KOLON (Saat, Tarih ve Dinamik QR Kod) ---
        left_box = QVBoxLayout()
        left_box.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_clock = QLabel("10:00:00")
        self.lbl_clock.setFont(QFont("Segoe UI", 48, QFont.Weight.Bold))
        self.lbl_clock.setStyleSheet("color: #f8fafc;")
        left_box.addWidget(self.lbl_clock, alignment=Qt.AlignmentFlag.AlignCenter)

        self.lbl_date = QLabel("6 Kasım 2026, Cuma")
        self.lbl_date.setFont(QFont("Segoe UI", 14))
        self.lbl_date.setStyleSheet("color: #94a3b8; margin-bottom: 20px;")
        left_box.addWidget(self.lbl_date, alignment=Qt.AlignmentFlag.AlignCenter)

        # QR Kod Çerçevesi
        qr_frame = QFrame()
        qr_frame.setStyleSheet("background: white; border-radius: 20px; padding: 15px;")
        qr_layout = QVBoxLayout(qr_frame)
        self.lbl_qr = QLabel()
        self.lbl_qr.setFixedSize(220, 220)
        self.lbl_qr.setScaledContents(True)
        qr_layout.addWidget(self.lbl_qr)
        left_box.addWidget(qr_frame, alignment=Qt.AlignmentFlag.AlignCenter)

        qr_hint = QLabel("📱 Telefonunuzla QR Kodu Okutun")
        qr_hint.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        qr_hint.setStyleSheet("color: #38bdf8; margin-top: 15px;")
        left_box.addWidget(qr_hint, alignment=Qt.AlignmentFlag.AlignCenter)

        body_layout.addLayout(left_box, 1)

        # --- SAĞ KOLON (Dokunmatik PIN Numpad) ---
        right_box = QVBoxLayout()
        right_box.setAlignment(Qt.AlignmentFlag.AlignCenter)

        pin_title = QLabel("Manuel Kilit Açma")
        pin_title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        pin_title.setStyleSheet("color: #f1f5f9; margin-bottom: 6px;")
        right_box.addWidget(pin_title, alignment=Qt.AlignmentFlag.AlignCenter)

        pin_desc = QLabel("İnternet kesintisinde ortak PIN'i giriniz:")
        pin_desc.setFont(QFont("Segoe UI", 11))
        pin_desc.setStyleSheet("color: #94a3b8; margin-bottom: 12px;")
        right_box.addWidget(pin_desc, alignment=Qt.AlignmentFlag.AlignCenter)

        # PIN Gösterge Ekranı
        self.pin_display = QLabel("• • • •")
        self.pin_display.setFixedHeight(50)
        self.pin_display.setFixedWidth(280)
        self.pin_display.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        self.pin_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pin_display.setStyleSheet("""
            background: #0f172a;
            border: 2px solid #334155;
            border-radius: 12px;
            color: #38bdf8;
            letter-spacing: 10px;
        """)
        right_box.addWidget(self.pin_display, alignment=Qt.AlignmentFlag.AlignCenter)

        # Numpad Izgarası
        numpad_grid = QGridLayout()
        numpad_grid.setSpacing(12)

        buttons = [
            ("1", 0, 0), ("2", 0, 1), ("3", 0, 2),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
            ("7", 2, 0), ("8", 2, 1), ("9", 2, 2),
            ("C", 3, 0), ("0", 3, 1), ("🔓", 3, 2),
        ]

        for text, row, col in buttons:
            btn = QPushButton(text)
            btn.setFixedSize(80, 65)
            btn.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
            if text == "🔓":
                btn.setStyleSheet("""
                    QPushButton { background: #10b981; color: white; border-radius: 12px; }
                    QPushButton:pressed { background: #059669; }
                """)
                btn.clicked.connect(self.verify_pin)
            elif text == "C":
                btn.setStyleSheet("""
                    QPushButton { background: #ef4444; color: white; border-radius: 12px; }
                    QPushButton:pressed { background: #dc2626; }
                """)
                btn.clicked.connect(self.clear_pin)
            else:
                btn.setStyleSheet("""
                    QPushButton { background: #1e293b; color: white; border-radius: 12px; border: 1px solid #334155; }
                    QPushButton:pressed { background: #38bdf8; color: black; }
                """)
                btn.clicked.connect(lambda _, t=text: self.append_pin(t))

            numpad_grid.addWidget(btn, row, col)

        right_box.addLayout(numpad_grid)
        body_layout.addLayout(right_box, 1)

        main_layout.addWidget(body, 1)

        # Zamanlayıcılar (Saat ve QR yenileme)
        self.timer_clock = QTimer(self)
        self.timer_clock.timeout.connect(self.update_clock)
        self.timer_clock.start(1000)
        self.update_clock()

        self.timer_qr = QTimer(self)
        self.timer_qr.timeout.connect(self.generate_qr)
        self.timer_qr.start(30000)  # Her 30 saniyede bir yeni QR kod
        self.generate_qr()

        # 4. Kilit Ekranına Gömülü Duyuru Katmanı (Görev çubuğunun çıkmasını kesin engeller)
        self.announcement_overlay = AnnouncementOverlayWidget(self)
        self.announcement_overlay.hide()

    # -------------------------------------------------------------
    # 🛡️ Kiosk Modu & Öğrenci Güvenlik Koruması
    # -------------------------------------------------------------
    def setup_kiosk_security(self):
        """Pardus ETAP üzerinde öğrencilerin kilit ekranını aşmasını engelleyen güvenlik koruması."""
        # 1 saniyelik bekçi (watchdog): Herhangi bir nedenle pencere odağı kaybolursa veya minimize edilirse anında öne çeker
        self.kiosk_watchdog = QTimer(self)
        self.kiosk_watchdog.timeout.connect(self.enforce_kiosk_watchdog)
        self.kiosk_watchdog.start(1000)

    def enforce_kiosk_watchdog(self):
        if self.is_locked:
            if self.isMinimized() or not self.isActiveWindow():
                self.restore_kiosk_fullscreen()

    def show_kiosk_fullscreen(self):
        """Tam ekran kiosk modunu başlatır ve klavyeyi kilitler."""
        screen = QApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.geometry())
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        # Klavyeyi kilit ekranına kilitle (Windows+D, Alt+Tab, Alt+F4, Ctrl+Alt+T engelleme)
        try:
            self.grabKeyboard()
        except Exception:
            pass
        if hasattr(self, "announcement_overlay") and self.announcement_overlay:
            self.announcement_overlay.setGeometry(0, 0, self.width(), self.height())

    def restore_kiosk_fullscreen(self):
        if not self.is_locked:
            return
        self.show_kiosk_fullscreen()

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange and self.is_locked:
            if self.isMinimized() or not (self.windowState() & Qt.WindowState.WindowFullScreen):
                QTimer.singleShot(10, self.restore_kiosk_fullscreen)
        super().changeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "announcement_overlay") and self.announcement_overlay:
            self.announcement_overlay.setGeometry(0, 0, self.width(), self.height())

    # -------------------------------------------------------------
    # 🕒 Saat & Dinamik QR Kod
    # -------------------------------------------------------------
    def update_clock(self):
        now = datetime.now()
        self.lbl_clock.setText(now.strftime("%H:%M:%S"))
        # Türkçe gün ve ay isimleri
        gunler = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
        aylar = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
        gun_str = gunler[now.weekday()]
        ay_str = aylar[now.month - 1]
        self.lbl_date.setText(f"{now.day} {ay_str} {now.year}, {gun_str}")

    def generate_qr(self):
        # QR Kod İçeriği: etap://unlock?board=cihaz_id&name=9-A&t=...
        import urllib.parse
        encoded_name = urllib.parse.quote(self.sinif_adi)
        qr_content = f"etap://unlock?board={self.cihaz_id}&name={encoded_name}&t={int(time.time())}"

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(qr_content)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#0f172a", back_color="white")

        # PIL Image -> QPixmap
        img = img.convert("RGBA")
        data = img.tobytes("raw", "RGBA")
        qim = QImage(data, img.size[0], img.size[1], QImage.Format.Format_RGBA8888)
        self.lbl_qr.setPixmap(QPixmap.fromImage(qim))

    # -------------------------------------------------------------
    # 🔢 PIN Numpad İşlemleri
    # -------------------------------------------------------------
    def append_pin(self, digit: str):
        if len(self.entered_pin) < 8:
            self.entered_pin += digit
            self.pin_display.setText("• " * len(self.entered_pin))

    def clear_pin(self):
        self.entered_pin = ""
        self.pin_display.setText("• • • •")

    def verify_pin(self):
        # Çevrimdışı TOTP Şifresi Hesapla (Telefondaki kodla birebir eşleşir)
        now_sec = int(time.time())
        step = now_sec // 30
        secret_salt = 7919
        totp_code = str((step * secret_salt + 104729) % 10000).zfill(4)

        if self.entered_pin == self.ogretmen_pin or self.entered_pin == totp_code or self.entered_pin == self.yonetici_sifre:
            self.clear_pin()
            self.unlock_board(by="Manuel PIN")
        else:
            self.pin_display.setText("HATALI")
            QTimer.singleShot(1000, self.clear_pin)

    # -------------------------------------------------------------
    # 🔓 Kilit Aç / 🔒 Kilitle Kontrolü
    # -------------------------------------------------------------
    def unlock_board(self, by: str = "Uzaktan"):
        self.is_locked = False
        try:
            self.releaseKeyboard()
        except Exception:
            pass
        if hasattr(self, "announcement_overlay") and self.announcement_overlay:
            self.announcement_overlay.hide()
        self.hide()  # Kilit ekranını gizle, masaüstü açılsın!

        # Masaüstünde küçük bir yeniden kilitleme butonu / tepsi simgesi göster
        self.show_floating_relock_button()

    def lock_board(self):
        self.is_locked = True
        if hasattr(self, "relock_btn") and self.relock_btn:
            self.relock_btn.hide()
        self.show_kiosk_fullscreen()

    def show_floating_relock_button(self):
        """Masaüstü açıkken sağ alt köşede duran minik 'Kilitle' butonu"""
        if hasattr(self, "relock_btn") and self.relock_btn:
            self.relock_btn.show()
            return

        self.relock_btn = QPushButton("🔒 Tahtayı Kilitle")
        self.relock_btn.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.relock_btn.setStyleSheet("""
            QPushButton {
                background: #ef4444;
                color: white;
                font-weight: bold;
                padding: 10px 16px;
                border-radius: 8px;
                font-size: 13px;
            }
            QPushButton:hover { background: #dc2626; }
        """)
        self.relock_btn.clicked.connect(self.lock_board)

        # Sağ alt köşeye konumlandır
        screen_geo = QApplication.primaryScreen().geometry()
        self.relock_btn.move(screen_geo.width() - 170, screen_geo.height() - 70)
        self.relock_btn.show()

    # -------------------------------------------------------------
    # 📡 Ağ ve WebSocket Olayları
    # -------------------------------------------------------------
    def init_network(self):
        self.ws_thread = WebSocketClientThread(self.sunucu_url, self.cihaz_id, self.sinif_adi)
        self.ws_thread.signal_status.connect(self.on_network_status_change)
        self.ws_thread.signal_command.connect(self.on_server_command)
        self.ws_thread.start()

    def on_network_status_change(self, is_online: bool):
        if is_online:
            self.lbl_status.setText("● Çevrimiçi")
            self.lbl_status.setStyleSheet("color: #34d399; background: rgba(16, 185, 129, 0.15); padding: 6px 14px; border-radius: 999px;")
        else:
            self.lbl_status.setText("● Çevrimdışı (PIN Modu)")
            self.lbl_status.setStyleSheet("color: #f87171; background: rgba(239, 68, 68, 0.15); padding: 6px 14px; border-radius: 999px;")

    def on_server_command(self, data: dict):
        action = data.get("action")
        if action == "unlock":
            self.unlock_board(by="Mobil Uygulama")
        elif action == "lock":
            self.lock_board()
        elif action == "poweroff":
            self.handle_poweroff()
        elif action == "banner_message":
            msg = data.get("message", "")
            duration = data.get("duration_sec", 45)
            self.show_announcement(msg, duration)

    def show_announcement(self, message: str, duration_sec: int = 45):
        # 1. Sesli melodi çal
        play_alert_sound()

        # 2. Üstteki mavi bandı da başlat
        self.banner.show_message(message, duration_sec)

        # 3. Kilitliyse: Dahili gömülü katmanda göster (Görev çubuğu KESİNLİKLE çıkmaz!)
        if self.is_locked:
            if hasattr(self, "announcement_overlay") and self.announcement_overlay:
                self.announcement_overlay.show_announcement(message, duration_sec)
        else:
            # Tahta açıksa: Masaüstünde yüzen şık bildirim penceresi aç
            dlg = AnnouncementModalDialog(message, duration_sec, None)
            dlg.show()

    def handle_poweroff(self):
        """Tahtanın gücünü kapatır (shutdown)."""
        dlg = QDialog(self)
        dlg.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        dlg.setStyleSheet("background: #0f172a; border: 2px solid #ef4444; border-radius: 20px; padding: 25px;")
        l = QVBoxLayout(dlg)
        icon = QLabel("🔌")
        icon.setFont(QFont("Segoe UI Emoji", 40))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(icon)
        t = QLabel("Akıllı Tahta Kapatılıyor...")
        t.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        t.setStyleSheet("color: #f87171;")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(t)
        sub = QLabel("Sistem gücü kesiliyor, lütfen bekleyiniz.")
        sub.setFont(QFont("Segoe UI", 12))
        sub.setStyleSheet("color: #94a3b8;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(sub)
        dlg.show()
        QApplication.processEvents()

        QTimer.singleShot(1800, self.execute_poweroff_command)

    def execute_poweroff_command(self):
        if sys.platform == "win32":
            os.system("shutdown /s /t 2")
        else:
            os.system("systemctl poweroff || shutdown -h now || poweroff")

    # -------------------------------------------------------------
    # ⚙️ Ayarlar
    # -------------------------------------------------------------
    def open_settings(self):
        # Önce yönetici şifresini doğrula
        pwd, ok = QLineEdit(), False
        # Basit onay
        if self.entered_pin == self.yonetici_sifre or self.entered_pin == self.ogretmen_pin:
            self.clear_pin()
            try:
                self.releaseKeyboard()
            except Exception:
                pass
            dlg = SettingsDialog(self.sinif_adi, self.sunucu_url, self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                new_board = dlg.input_board.text().strip() or "9-A"
                new_url = dlg.input_url.text().strip()
                old_name = self.sinif_adi
                old_url = self.sunucu_url

                self.sinif_adi = new_board
                self.sunucu_url = new_url
                self.cfg.set("GENEL", "sinif_adi", self.sinif_adi)
                self.cfg.set("GENEL", "sunucu_ws_url", self.sunucu_url)
                
                # Dosyaya kalıcı kaydet
                saved = save_config(self.cfg)
                if not saved:
                    print("⚠️ Uyarı: Config dosyasına yazılamadı.")
                
                # Ekranda tahta adını anında güncelle
                self.lbl_class.setText(f"🖥️ {self.sinif_adi}")
                self.generate_qr()
                
                # Sunucu adresi değiştiyse baştan başlat
                if new_url != old_url:
                    if hasattr(self, "ws_thread") and self.ws_thread:
                        self.ws_thread.stop()
                    self.init_network()
                else:
                    # Sadece sınıf adı değiştiyse bağlantıyı ASLA koparma! Anlık canlı güncelleme gönder
                    updated = False
                    if hasattr(self, "ws_thread") and self.ws_thread:
                        updated = self.ws_thread.send_name_update(self.sinif_adi)
                    if not updated:
                        if hasattr(self, "ws_thread") and self.ws_thread:
                            self.ws_thread.stop()
                        self.init_network()

                QMessageBox.information(
                    self,
                    "Ayarlar Kaydedildi",
                    f"✅ Tahta adı '{self.sinif_adi}' olarak güncellendi ve sunucuya anında bildirildi!"
                )
            if self.is_locked:
                self.show_kiosk_fullscreen()
        else:
            self.pin_display.setText("ŞİFRE GİRİN")
            QTimer.singleShot(1500, self.clear_pin)

    # -------------------------------------------------------------
    # 🛑 Sistem Tuşlarını Engelleme (Kiosk Güvenliği)
    # -------------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent):
        if not self.is_locked:
            super().keyPressEvent(event)
            return

        # 1. Yetkili / Yönetici Acil Çıkış Kısayolu: Ctrl + Shift + Q
        # ÖĞRENCİ ENGELİ: Şifresiz doğrudan kapanamaz!
        if (event.modifiers() == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier) 
            and event.key() == Qt.Key.Key_Q):
            self.prompt_admin_exit()
            return

        # 2. Fiziksel klavyeden rakam tuşları (0-9 ve Numpad 0-9)
        key = event.key()
        text = event.text()
        if key in [Qt.Key.Key_0, Qt.Key.Key_1, Qt.Key.Key_2, Qt.Key.Key_3, Qt.Key.Key_4,
                   Qt.Key.Key_5, Qt.Key.Key_6, Qt.Key.Key_7, Qt.Key.Key_8, Qt.Key.Key_9]:
            self.append_pin(text)
            return

        # 3. Enter / Return: PIN'i doğrula
        if key in [Qt.Key.Key_Return, Qt.Key.Key_Enter]:
            self.verify_pin()
            return

        # 4. Backspace / Delete: Son karakteri sil veya temizle
        if key == Qt.Key.Key_Backspace:
            if len(self.entered_pin) > 0:
                self.entered_pin = self.entered_pin[:-1]
                self.pin_display.setText("• " * len(self.entered_pin) if self.entered_pin else "• • • •")
            return
        if key == Qt.Key.Key_Delete:
            self.clear_pin()
            return

        # 5. TÜM DİĞER SİSTEM KISAYOLLARINI BLOKE ET:
        # Windows (Super) tuşu, Windows+D, Alt+Tab, Alt+F4, Ctrl+Alt+T, Esc, F11 vb.
        event.ignore()

    def prompt_admin_exit(self):
        """Yalnızca yönetici şifresini (yonetici_sifre) bilen yetkilinin programı sonlandırmasına izin verir."""
        try:
            self.releaseKeyboard()
        except Exception:
            pass
        pwd, ok = QInputDialog.getText(
            self,
            "Yönetici Çıkışı",
            "Kilit ekranını tamamen kapatmak için YÖNETİCİ şifresini girin:",
            QLineEdit.EchoMode.Password
        )
        if ok and pwd == self.yonetici_sifre:
            self.is_locked = False
            QApplication.quit()
        else:
            if ok:
                QMessageBox.warning(self, "Yetkisiz Erişim", "Hatalı yönetici şifresi! Kilit ekranı kapatılamaz.")
            self.show_kiosk_fullscreen()

    def closeEvent(self, event):
        # Kullanıcının pencereyi kapatmasını engelle
        if self.is_locked:
            event.ignore()
        else:
            try:
                self.releaseKeyboard()
            except Exception:
                pass
            event.accept()


# -------------------------------------------------------------
# 🚀 Başlatıcı
# -------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    window = LockScreenWindow()
    window.show_kiosk_fullscreen()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
