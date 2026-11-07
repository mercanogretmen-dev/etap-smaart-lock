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
                print(f"[CONFIG] En guncel dosyadan yuklendi: {p}")
                break
            except Exception as e:
                print(f"[CONFIG] Okuma hatasi [{p}]: {e}")

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
            print(f"[CONFIG] Kaydedildi: {p}")
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
                print(f"[WS] Isim guncellemesi gonderildi: {new_name}")
                return True
            except Exception as e:
                print(f"[WS] Isim gonderme hatasi: {e}")
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
# 📢 Masaüstü Açıkken Ortada Açılan Modern İdare Duyuru Kutusu (Popup)
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
        self.setFixedSize(680, 380)
        self.setStyleSheet("background-color: #0f172a; border-radius: 24px;")

        self.duration_left = duration_sec

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.frame = QFrame()
        self.frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0f172a, stop:1 #1e293b);
                border: 3px solid #38bdf8;
                border-radius: 24px;
            }
        """)
        frame_layout = QVBoxLayout(self.frame)
        frame_layout.setContentsMargins(35, 26, 35, 25)
        frame_layout.setSpacing(16)

        # Üst Başlık & Kapat Butonu
        header = QHBoxLayout()
        icon = QLabel("📢")
        icon.setFont(QFont("Segoe UI Emoji", 26))
        icon.setStyleSheet("border: none; background: transparent;")
        header.addWidget(icon)

        title = QLabel("MÜDÜR / İDARE DUYURUSU")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.ExtraBold))
        title.setStyleSheet("color: #38bdf8; letter-spacing: 1.5px; border: none; background: transparent;")
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
        btn_close_top.clicked.connect(self.close_dialog)
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
        self.lbl_countdown.setStyleSheet("color: #94a3b8; border: none; background: transparent;")
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
        btn_dismiss.clicked.connect(self.close_dialog)
        bottom.addWidget(btn_dismiss)
        frame_layout.addLayout(bottom)

        layout.addWidget(self.frame)

        # Geri sayım zamanlayıcısı
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)

    def show_centered_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.geometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + (geo.height() - self.height()) // 2
            self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

    def close_dialog(self):
        self.timer.stop()
        self.hide()
        self.close()

    def tick(self):
        self.duration_left -= 1
        if self.duration_left <= 0:
            self.close_dialog()
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
# ⚙️ Kilit Ekranı İçine Gömülü Ayarlar Katmanı (In-Window Overlay)
# Bu katman kilit ekranının İÇİNDE çizildiği için asla arkada açılmaz!
# Hem fiziksel klavye hem de dokunmatik sanal klavye destekler.
# -------------------------------------------------------------
class SettingsOverlayWidget(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.lock_window = parent
        self.active_input = None
        self.init_ui()
        self.hide()

    def init_ui(self):
        self.setStyleSheet("background: rgba(0, 0, 0, 0.85);")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(20, 20, 20, 20)

        card = QFrame()
        card.setFixedSize(680, 610)
        card.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0f172a, stop:1 #1e293b);
                border: 2px solid #38bdf8;
                border-radius: 24px;
            }
        """)
        glow = QGraphicsDropShadowEffect(card)
        glow.setBlurRadius(50)
        glow.setColor(QColor(56, 189, 248, 190))
        glow.setOffset(0, 4)
        card.setGraphicsEffect(glow)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 22, 32, 22)
        card_layout.setSpacing(10)

        # Başlık ve Kapat Butonu
        header = QHBoxLayout()
        icon = QLabel("⚙️")
        icon.setFont(QFont("Segoe UI Emoji", 24))
        icon.setStyleSheet("border: none; background: transparent;")
        header.addWidget(icon)

        title = QLabel("SİSTEM VE SINIF AYARLARI")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.ExtraBold))
        title.setStyleSheet("color: #38bdf8; letter-spacing: 1px; border: none; background: transparent;")
        header.addWidget(title)
        header.addStretch()

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(36, 36)
        btn_close.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        btn_close.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 18px;
            }
            QPushButton:hover { background: #ef4444; color: white; border-color: #ef4444; }
        """)
        btn_close.clicked.connect(self.hide_overlay)
        header.addWidget(btn_close)
        card_layout.addLayout(header)

        # 1. Sınıf / Tahta Adı
        lbl_b = QLabel("🖥️ Sınıf / Tahta Adı (Düzenlemek için kutuya dokunun veya klavyeden yazın):")
        lbl_b.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        lbl_b.setStyleSheet("color: #e2e8f0; border: none; background: transparent;")
        card_layout.addWidget(lbl_b)

        self.input_board = QLineEdit()
        self.input_board.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.input_board.setFixedHeight(44)
        self.input_board.installEventFilter(self)
        card_layout.addWidget(self.input_board)

        # 2. Sunucu WebSocket URL
        lbl_u = QLabel("🌐 Sunucu WebSocket Adresi:")
        lbl_u.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl_u.setStyleSheet("color: #cbd5e1; border: none; background: transparent;")
        card_layout.addWidget(lbl_u)

        self.input_url = QLineEdit()
        self.input_url.setFont(QFont("Segoe UI", 11))
        self.input_url.setFixedHeight(40)
        self.input_url.installEventFilter(self)
        card_layout.addWidget(self.input_url)

        self.active_input = self.input_board
        self._update_input_styles()

        # Dokunmatik Sanal Klavye (Tahta Üzerinde Kolay Sınıf Adı Yazımı İçin)
        kb_frame = QFrame()
        kb_frame.setStyleSheet("background: rgba(15, 23, 42, 0.75); border: 1px solid #334155; border-radius: 14px; padding: 6px;")
        kb_layout = QVBoxLayout(kb_frame)
        kb_layout.setContentsMargins(8, 8, 8, 8)
        kb_layout.setSpacing(6)

        rows = [
            ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-"],
            ["A", "B", "C", "D", "E", "F", "G", "H", "I", "K", "L"],
            ["M", "N", "O", "P", "R", "S", "T", "U", "V", "Y", "Z"],
        ]
        for r in rows:
            row_layout = QHBoxLayout()
            row_layout.setSpacing(5)
            for ch in r:
                b = QPushButton(ch)
                b.setFixedHeight(36)
                b.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
                b.setStyleSheet("""
                    QPushButton {
                        background: #1e293b; color: #f8fafc;
                        border: 1px solid #475569; border-radius: 8px;
                    }
                    QPushButton:pressed { background: #38bdf8; color: #0f172a; }
                """)
                b.clicked.connect(lambda _, c=ch: self._append_char(c))
                row_layout.addWidget(b)
            kb_layout.addLayout(row_layout)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        for preset in ["9-A", "9-B", "10-A", "11-A", "12-A"]:
            pb = QPushButton(preset)
            pb.setFixedHeight(34)
            pb.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            pb.setStyleSheet("""
                QPushButton {
                    background: rgba(56, 189, 248, 0.15); color: #38bdf8;
                    border: 1px solid rgba(56, 189, 248, 0.35); border-radius: 8px;
                }
                QPushButton:pressed { background: #38bdf8; color: #0f172a; }
            """)
            pb.clicked.connect(lambda _, p=preset: self.input_board.setText(p))
            action_row.addWidget(pb)

        btn_bs = QPushButton("⌫ Sil")
        btn_bs.setFixedHeight(34)
        btn_bs.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        btn_bs.setStyleSheet("""
            QPushButton { background: #f59e0b; color: #0f172a; border-radius: 8px; border: none; }
            QPushButton:pressed { background: #d97706; }
        """)
        btn_bs.clicked.connect(self._backspace_char)
        action_row.addWidget(btn_bs)

        btn_clr = QPushButton("Temizle")
        btn_clr.setFixedHeight(34)
        btn_clr.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        btn_clr.setStyleSheet("""
            QPushButton { background: #ef4444; color: #ffffff; border-radius: 8px; border: none; }
            QPushButton:pressed { background: #dc2626; }
        """)
        btn_clr.clicked.connect(self._clear_active)
        action_row.addWidget(btn_clr)

        kb_layout.addLayout(action_row)
        card_layout.addWidget(kb_frame)

        # Bilgi Notu
        self.lbl_status = QLabel("💡 Not: İsim değiştiğinde sunucu bağlantısı kopmaz, anında güncellenir.")
        self.lbl_status.setFont(QFont("Segoe UI", 10))
        self.lbl_status.setStyleSheet("color: #94a3b8; border: none; background: transparent;")
        card_layout.addWidget(self.lbl_status)

        # Butonlar
        btn_box = QHBoxLayout()
        btn_box.setSpacing(12)

        btn_save = QPushButton("💾 Değişiklikleri Kaydet (Enter)")
        btn_save.setFixedHeight(44)
        btn_save.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        btn_save.setStyleSheet("""
            QPushButton {
                background: #10b981;
                color: #ffffff;
                border-radius: 12px;
                border: none;
            }
            QPushButton:hover { background: #059669; }
            QPushButton:pressed { background: #047857; }
        """)
        btn_save.clicked.connect(self.save_settings)
        btn_box.addWidget(btn_save, 2)

        btn_cancel = QPushButton("İptal (Esc)")
        btn_cancel.setFixedHeight(44)
        btn_cancel.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        btn_cancel.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: #cbd5e1;
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.15); color: #fff; }
        """)
        btn_cancel.clicked.connect(self.hide_overlay)
        btn_box.addWidget(btn_cancel, 1)

        card_layout.addLayout(btn_box)
        layout.addWidget(card)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            if obj in (self.input_board, self.input_url):
                self.active_input = obj
                self._update_input_styles()
        return super().eventFilter(obj, event)

    def _update_input_styles(self):
        active_css = """
            QLineEdit {
                background: #0b1120;
                color: #ffffff;
                border: 2.5px solid #38bdf8;
                border-radius: 10px;
                padding: 0 14px;
            }
        """
        inactive_css = """
            QLineEdit {
                background: #0b1120;
                color: #94a3b8;
                border: 1.5px solid #334155;
                border-radius: 10px;
                padding: 0 14px;
            }
        """
        if self.active_input == self.input_url:
            self.input_board.setStyleSheet(inactive_css)
            self.input_url.setStyleSheet(active_css)
        else:
            self.input_board.setStyleSheet(active_css)
            self.input_url.setStyleSheet(inactive_css)

    def _append_char(self, ch: str):
        target = self.active_input or self.input_board
        target.setText(target.text() + ch)

    def _backspace_char(self):
        target = self.active_input or self.input_board
        t = target.text()
        if t:
            target.setText(t[:-1])

    def _clear_active(self):
        target = self.active_input or self.input_board
        target.clear()

    def handle_key_event(self, event: QKeyEvent):
        """Ana pencereden yakalanan fiziksel klavye tuşlarını doğrudan aktif kutuya yazar."""
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.hide_overlay()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.save_settings()
            return
        if key in (Qt.Key.Key_Tab, Qt.Key.Key_Down, Qt.Key.Key_Up):
            self.active_input = self.input_url if self.active_input == self.input_board else self.input_board
            self._update_input_styles()
            return
        if key == Qt.Key.Key_Backspace:
            self._backspace_char()
            return
        if key == Qt.Key.Key_Delete:
            self._clear_active()
            return

        text = event.text()
        if text and len(text) == 1 and text.isprintable():
            self._append_char(text)

    def show_settings(self):
        self.input_board.setText(self.lock_window.sinif_adi)
        self.input_url.setText(self.lock_window.sunucu_url)
        self.active_input = self.input_board
        self._update_input_styles()
        self.lbl_status.setText("💡 Not: İsim değiştiğinde sunucu bağlantısı kopmaz, anında güncellenir.")
        self.lbl_status.setStyleSheet("color: #94a3b8; border: none; background: transparent;")
        self.setGeometry(0, 0, self.lock_window.width(), self.lock_window.height())
        self.show()
        self.raise_()

    def hide_overlay(self):
        self.hide()
        if self.lock_window.is_locked:
            self.lock_window._ensure_keyboard_grab()

    def save_settings(self):
        new_name = self.input_board.text().strip() or "9-A"
        new_url = self.input_url.text().strip()
        self.lock_window.apply_new_settings(new_name, new_url)
        self.lbl_status.setText("✅ Ayarlar kaydedildi ve uygulandı!")
        self.lbl_status.setStyleSheet("color: #34d399; font-weight: bold; border: none; background: transparent;")
        QTimer.singleShot(600, self.hide_overlay)


# -------------------------------------------------------------
# 🛡️ Kilit Ekranı İçine Gömülü Yönetici Çıkış Katmanı (Ctrl+Shift+Q)
# Bu katman kilit ekranının İÇİNDE açılır, asla arkaya kaçmaz!
# Hem fiziksel klavye hem de dokunmatik tuşlarla şifre girilebilir.
# -------------------------------------------------------------
class AdminExitOverlayWidget(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.lock_window = parent
        self.init_ui()
        self.hide()

    def init_ui(self):
        self.setStyleSheet("background: rgba(0, 0, 0, 0.88);")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(20, 20, 20, 20)

        card = QFrame()
        card.setFixedSize(560, 490)
        card.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1e1b2e, stop:1 #0f172a);
                border: 2px solid #ef4444;
                border-radius: 24px;
            }
        """)
        glow = QGraphicsDropShadowEffect(card)
        glow.setBlurRadius(50)
        glow.setColor(QColor(239, 68, 68, 180))
        glow.setOffset(0, 4)
        card.setGraphicsEffect(glow)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 24, 32, 24)
        card_layout.setSpacing(12)

        # Başlık
        header = QHBoxLayout()
        icon = QLabel("🛡️")
        icon.setFont(QFont("Segoe UI Emoji", 26))
        icon.setStyleSheet("border: none; background: transparent;")
        header.addWidget(icon)

        title = QLabel("YÖNETİCİ ÇIKIŞI")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.ExtraBold))
        title.setStyleSheet("color: #f87171; letter-spacing: 1.5px; border: none; background: transparent;")
        header.addWidget(title)
        header.addStretch()

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(36, 36)
        btn_close.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        btn_close.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 18px;
            }
            QPushButton:hover { background: #ef4444; color: white; }
        """)
        btn_close.clicked.connect(self.hide_overlay)
        header.addWidget(btn_close)
        card_layout.addLayout(header)

        desc = QLabel("Kilit uygulamasını tamamen kapatmak için yönetici şifresini girin (Klavyeden veya dokunmatik tuşlarla):")
        desc.setFont(QFont("Segoe UI", 11))
        desc.setStyleSheet("color: #cbd5e1; border: none; background: transparent;")
        desc.setWordWrap(True)
        card_layout.addWidget(desc)

        self.input_pwd = QLineEdit()
        self.input_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_pwd.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.input_pwd.setFixedHeight(48)
        self.input_pwd.setPlaceholderText("Yönetici şifresi...")
        self.input_pwd.setStyleSheet("""
            QLineEdit {
                background: #0b1120;
                color: #ffffff;
                border: 2.5px solid #ef4444;
                border-radius: 12px;
                padding: 0 16px;
                letter-spacing: 4px;
            }
        """)
        card_layout.addWidget(self.input_pwd)

        # Dokunmatik Mini Tuş Takımı (Klavye olmadan da şifre girebilmek için)
        pad_frame = QFrame()
        pad_frame.setStyleSheet("background: rgba(15, 23, 42, 0.75); border: 1px solid #334155; border-radius: 14px;")
        pad_layout = QVBoxLayout(pad_frame)
        pad_layout.setContentsMargins(10, 8, 10, 8)
        pad_layout.setSpacing(6)

        row1 = QHBoxLayout()
        row1.setSpacing(5)
        for ch in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]:
            b = QPushButton(ch)
            b.setFixedHeight(36)
            b.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            b.setStyleSheet("""
                QPushButton { background: #1e293b; color: #fff; border: 1px solid #475569; border-radius: 8px; }
                QPushButton:pressed { background: #ef4444; color: #fff; }
            """)
            b.clicked.connect(lambda _, c=ch: self._append_char(c))
            row1.addWidget(b)
        pad_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(5)
        for ch in ["a", "d", "m", "i", "n", "e", "t", "p", "s", "_"]:
            b = QPushButton(ch)
            b.setFixedHeight(36)
            b.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            b.setStyleSheet("""
                QPushButton { background: #1e293b; color: #cbd5e1; border: 1px solid #475569; border-radius: 8px; }
                QPushButton:pressed { background: #ef4444; color: #fff; }
            """)
            b.clicked.connect(lambda _, c=ch: self._append_char(c))
            row2.addWidget(b)

        btn_bs = QPushButton("⌫ Sil")
        btn_bs.setFixedHeight(36)
        btn_bs.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        btn_bs.setStyleSheet("QPushButton { background: #f59e0b; color: #0f172a; border-radius: 8px; border: none; }")
        btn_bs.clicked.connect(self._backspace_char)
        row2.addWidget(btn_bs)

        btn_clr = QPushButton("Temizle")
        btn_clr.setFixedHeight(36)
        btn_clr.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        btn_clr.setStyleSheet("QPushButton { background: #475569; color: #fff; border-radius: 8px; border: none; }")
        btn_clr.clicked.connect(self.input_pwd.clear)
        row2.addWidget(btn_clr)

        pad_layout.addLayout(row2)
        card_layout.addWidget(pad_frame)

        self.lbl_error = QLabel("")
        self.lbl_error.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.lbl_error.setStyleSheet("color: #ef4444; border: none; background: transparent;")
        self.lbl_error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.lbl_error)

        # Butonlar
        btn_box = QHBoxLayout()
        btn_box.setSpacing(12)

        btn_exit = QPushButton("🛑 Kilit Ekranını Kapat (Enter)")
        btn_exit.setFixedHeight(45)
        btn_exit.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        btn_exit.setStyleSheet("""
            QPushButton {
                background: #ef4444;
                color: white;
                border-radius: 12px;
                border: none;
            }
            QPushButton:hover { background: #dc2626; }
            QPushButton:pressed { background: #b91c1c; }
        """)
        btn_exit.clicked.connect(self.verify_exit)
        btn_box.addWidget(btn_exit, 2)

        btn_cancel = QPushButton("İptal (Esc)")
        btn_cancel.setFixedHeight(45)
        btn_cancel.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        btn_cancel.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: #cbd5e1;
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.15); color: #fff; }
        """)
        btn_cancel.clicked.connect(self.hide_overlay)
        btn_box.addWidget(btn_cancel, 1)

        card_layout.addLayout(btn_box)
        layout.addWidget(card)

    def _append_char(self, ch: str):
        self.lbl_error.clear()
        self.input_pwd.setText(self.input_pwd.text() + ch)

    def _backspace_char(self):
        self.lbl_error.clear()
        t = self.input_pwd.text()
        if t:
            self.input_pwd.setText(t[:-1])

    def handle_key_event(self, event: QKeyEvent):
        """Ana pencereden yakalanan fiziksel klavye tuşlarını doğrudan şifre kutusuna yazar."""
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.hide_overlay()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.verify_exit()
            return
        if key == Qt.Key.Key_Backspace:
            self._backspace_char()
            return
        if key == Qt.Key.Key_Delete:
            self.input_pwd.clear()
            return

        text = event.text()
        if text and len(text) == 1 and text.isprintable():
            self._append_char(text)

    def show_prompt(self):
        self.input_pwd.clear()
        self.lbl_error.clear()
        self.setGeometry(0, 0, self.lock_window.width(), self.lock_window.height())
        self.show()
        self.raise_()

    def hide_overlay(self):
        self.hide()
        if self.lock_window.is_locked:
            self.lock_window._ensure_keyboard_grab()

    def verify_exit(self):
        pwd = self.input_pwd.text().strip()
        if pwd == self.lock_window.yonetici_sifre or pwd == self.lock_window.ogretmen_pin:
            self.lock_window.is_locked = False
            try:
                self.lock_window.releaseKeyboard()
            except Exception:
                pass
            QApplication.quit()
        else:
            self.lbl_error.setText("❌ Hatalı yönetici şifresi!")
            self.input_pwd.clear()


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
        self.settings_overlay = None
        self.admin_exit_overlay = None
        self.desktop_announcement_dlg = None

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

        # 4. Kilit Ekranına Gömülü Katmanlar (Asla arkada açılmaz ve görev çubuğunu tetiklemez!)
        self.announcement_overlay = AnnouncementOverlayWidget(self)
        self.announcement_overlay.hide()

        self.settings_overlay = SettingsOverlayWidget(self)
        self.settings_overlay.hide()

        self.admin_exit_overlay = AdminExitOverlayWidget(self)
        self.admin_exit_overlay.hide()

    # -------------------------------------------------------------
    # 🛡️ Kiosk Modu & Öğrenci Güvenlik Koruması
    # -------------------------------------------------------------
    def setup_kiosk_security(self):
        """Pardus ETAP üzerinde öğrencilerin kilit ekranını aşmasını engelleyen güvenlik koruması."""
        # 1 saniyelik bekçi (watchdog): Herhangi bir nedenle pencere odağı kaybolursa veya minimize edilirse anında öne çeker
        self.kiosk_watchdog = QTimer(self)
        self.kiosk_watchdog.timeout.connect(self.enforce_kiosk_watchdog)
        self.kiosk_watchdog.start(1000)

    def _ensure_keyboard_grab(self):
        if self.is_locked and self.isVisible():
            try:
                self.grabKeyboard()
            except Exception:
                pass

    def enforce_kiosk_watchdog(self):
        if self.is_locked:
            if self.isMinimized() or not self.isVisible():
                self.restore_kiosk_fullscreen()
            else:
                self.raise_()
                self._ensure_keyboard_grab()

    def show_kiosk_fullscreen(self):
        """Tam ekran kiosk modunu başlatır ve klavyeyi kilitler."""
        screen = QApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.geometry())
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        # Klavyeyi kilit ekranına kilitle (Windows+D, Alt+Tab, Alt+F4, Ctrl+Alt+T engelleme)
        self._ensure_keyboard_grab()
        QTimer.singleShot(150, self._ensure_keyboard_grab)
        for overlay in [self.announcement_overlay, self.settings_overlay, self.admin_exit_overlay]:
            if overlay:
                overlay.setGeometry(0, 0, self.width(), self.height())

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
        for overlay in [
            getattr(self, "announcement_overlay", None),
            getattr(self, "settings_overlay", None),
            getattr(self, "admin_exit_overlay", None)
        ]:
            if overlay:
                overlay.setGeometry(0, 0, self.width(), self.height())

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
        if hasattr(self, "desktop_announcement_dlg") and self.desktop_announcement_dlg:
            try:
                self.desktop_announcement_dlg.close_dialog()
            except Exception:
                pass
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
            # Tahta açıksa: Masaüstünün tam ortasında üstte kalan bildirim penceresi aç
            if hasattr(self, "desktop_announcement_dlg") and self.desktop_announcement_dlg:
                try:
                    self.desktop_announcement_dlg.close_dialog()
                except Exception:
                    pass
            self.desktop_announcement_dlg = AnnouncementModalDialog(message, duration_sec, None)
            self.desktop_announcement_dlg.show_centered_on_screen()

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
    # ⚙️ Ayarlar (In-Window Katman)
    # -------------------------------------------------------------
    def open_settings(self):
        # Basit onay: Numpadde yönetici veya öğretmen şifresi yazılmışsa doğrudan katmanı aç
        if self.entered_pin == self.yonetici_sifre or self.entered_pin == self.ogretmen_pin:
            self.clear_pin()
            if hasattr(self, "settings_overlay") and self.settings_overlay:
                self.settings_overlay.show_settings()
        else:
            self.pin_display.setText("ŞİFRE GİRİN")
            QTimer.singleShot(1500, self.clear_pin)

    def apply_new_settings(self, new_board: str, new_url: str):
        old_name = self.sinif_adi
        old_url = self.sunucu_url

        self.sinif_adi = new_board
        self.sunucu_url = new_url
        self.cfg.set("GENEL", "sinif_adi", self.sinif_adi)
        self.cfg.set("GENEL", "sunucu_ws_url", self.sunucu_url)
        save_config(self.cfg)

        self.lbl_class.setText(f"🖥️ {self.sinif_adi}")
        self.generate_qr()

        if new_url != old_url:
            if hasattr(self, "ws_thread") and self.ws_thread:
                self.ws_thread.stop()
            self.init_network()
        else:
            updated = False
            if hasattr(self, "ws_thread") and self.ws_thread:
                updated = self.ws_thread.send_name_update(self.sinif_adi)
            if not updated:
                if hasattr(self, "ws_thread") and self.ws_thread:
                    self.ws_thread.stop()
                self.init_network()

    # -------------------------------------------------------------
    # 🛑 Sistem Tuşlarını Engelleme & Doğrudan Klavye Yönlendirme
    # -------------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent):
        if not self.is_locked:
            super().keyPressEvent(event)
            return

        # 1. Açık bir katman (Ayarlar veya Yönetici Çıkışı) varsa, tuşları DOĞRUDAN o katmana ilet!
        # (grabKeyboard aktifken Qt odak yönlendirmesi yerine doğrudan handle_key_event çağrılır)
        if hasattr(self, "settings_overlay") and self.settings_overlay and self.settings_overlay.isVisible():
            self.settings_overlay.handle_key_event(event)
            return

        if hasattr(self, "admin_exit_overlay") and self.admin_exit_overlay and self.admin_exit_overlay.isVisible():
            self.admin_exit_overlay.handle_key_event(event)
            return

        # 2. Yetkili / Yönetici Acil Çıkış Kısayolu: Ctrl + Shift + Q (Dahili şifre ekranını açar)
        if (event.modifiers() == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier) 
            and event.key() == Qt.Key.Key_Q):
            if hasattr(self, "admin_exit_overlay") and self.admin_exit_overlay:
                self.admin_exit_overlay.show_prompt()
            return

        # 3. Fiziksel klavyeden rakam ve harf tuşları (0-9, Numpad 0-9, admin123 vb.)
        key = event.key()
        text = event.text()
        if key in [Qt.Key.Key_0, Qt.Key.Key_1, Qt.Key.Key_2, Qt.Key.Key_3, Qt.Key.Key_4,
                   Qt.Key.Key_5, Qt.Key.Key_6, Qt.Key.Key_7, Qt.Key.Key_8, Qt.Key.Key_9]:
            digit_char = text if (text and text.isdigit()) else chr(ord('0') + (key - Qt.Key.Key_0))
            self.append_pin(digit_char)
            return

        if text and len(text) == 1 and text.isalnum():
            self.append_pin(text)
            return

        # 4. Enter / Return: PIN'i doğrula
        if key in [Qt.Key.Key_Return, Qt.Key.Key_Enter]:
            self.verify_pin()
            return

        # 5. Backspace / Delete: Son karakteri sil veya temizle
        if key == Qt.Key.Key_Backspace:
            if len(self.entered_pin) > 0:
                self.entered_pin = self.entered_pin[:-1]
                self.pin_display.setText("• " * len(self.entered_pin) if self.entered_pin else "• • • •")
            return
        if key == Qt.Key.Key_Delete:
            self.clear_pin()
            return

        # 6. TÜM DİĞER SİSTEM KISAYOLLARINI BLOKE ET (Windows, Alt+Tab, Alt+F4, Esc, F11 vb.)
        event.ignore()

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
