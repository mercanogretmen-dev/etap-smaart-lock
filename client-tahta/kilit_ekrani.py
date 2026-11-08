#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TAHTA KİLİT (Etkileşimli Tahta Kilit Uygulaması) — v1.1
Geliştirici: MERCAN ROBOTİK (mercanrobotik)
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
from PIL import Image, ImageDraw

try:
    import websockets
except ImportError:
    websockets = None

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QTime, QDate, QProcess, QEvent, QRectF, QPointF, QLockFile, QStandardPaths
from PyQt6.QtGui import QRegion
from PyQt6.QtGui import (
    QFont, QPixmap, QImage, QKeyEvent, QColor, QIcon,
    QPainter, QPainterPath, QLinearGradient, QRadialGradient, QPen, QBrush, QFontMetrics
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QGridLayout, QLineEdit, QDialog, QInputDialog,
    QMessageBox, QFrame, QGraphicsDropShadowEffect, QProgressBar, QSizePolicy
)

APP_NAME = "Tahta Kilit"
APP_SUBTITLE = "Etkileşimli Tahta Kilit Uygulaması"
DEVELOPER_NAME = "MERCAN ROBOTİK"
APP_VERSION = "v1.1.3"

# Platforma duyarlı kalıcı ayar dizinleri
if sys.platform == "win32":
    WIN_PROGRAMDATA = os.environ.get("ProgramData", "C:\\ProgramData")
    WIN_APPDATA = os.environ.get("APPDATA", os.path.expanduser("~\\AppData\\Roaming"))
    SYSTEM_CONFIG_DIR = os.path.join(WIN_PROGRAMDATA, "TahtaKilit")
    USER_CONFIG_DIR = os.path.join(WIN_APPDATA, "TahtaKilit")
else:
    SYSTEM_CONFIG_DIR = "/etc/etap-smartlock"
    USER_CONFIG_DIR = os.path.expanduser("~/.config/etap-smartlock")

SYSTEM_CONFIG_PATH = os.path.join(SYSTEM_CONFIG_DIR, "config.ini")
USER_CONFIG_PATH = os.path.join(USER_CONFIG_DIR, "config.ini")

# PyInstaller tek parça .exe veya standart .py çalışma dizini
if getattr(sys, "frozen", False):
    BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    EXE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    EXE_DIR = BASE_DIR

LOCAL_CONFIG_PATH = os.path.join(EXE_DIR, "config.ini")


def get_asset_path(filename: str) -> str:
    """Görsel ve ikon dosyalarının tam yolunu döner (PyInstaller, Pardus /opt ve Windows uyumlu)."""
    candidates = [
        os.path.join(BASE_DIR, "assets", filename),
        os.path.join(EXE_DIR, "assets", filename),
        os.path.join("/opt/etap-smartlock/assets", filename),
        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Tahta Kilit", "assets", filename) if sys.platform == "win32" else "",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return os.path.join(BASE_DIR, "assets", filename)


def get_config_search_paths():
    """Tüm olası konfigürasyon yollarını öncelik sırasıyla döner."""
    return [
        USER_CONFIG_PATH,
        SYSTEM_CONFIG_PATH,
        LOCAL_CONFIG_PATH
    ]


def load_config():
    config = configparser.ConfigParser()

    existing_paths = [p for p in get_config_search_paths() if os.path.exists(p)]
    if existing_paths:
        existing_paths.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        for p in existing_paths:
            try:
                config.read(p, encoding="utf-8")
                print(f"[CONFIG] En guncel dosyadan yuklendi: {p}")
                break
            except Exception as e:
                print(f"[CONFIG] Okuma hatasi [{p}]: {e}")

    if "GENEL" not in config:
        config["GENEL"] = {}

    defaults = {
        "sinif_adi": "9-A",
        "okul_adi": "T.C. MİLLÎ EĞİTİM BAKANLIĞI — ETKİLEŞİMLİ TAHTA SİSTEMİ",
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

    if not dev_id:
        import uuid
        dev_id = f"etap-{uuid.uuid4().hex[:8]}"

    config.set("GENEL", "cihaz_id", dev_id)
    save_config(config)
    return dev_id


def save_config(config):
    """
    Ayarları kalıcı olarak TÜM erişilebilir konfigürasyon yollarına (/etc, ~/.config, yerel) kaydeder.
    Böylece tahta yeniden başlatılsa bile yeni isim ve okul adı asla kaybolmaz.
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
            try:
                os.chmod(p, 0o666)
            except Exception:
                pass
            saved_any = True
            print(f"[CONFIG] Kaydedildi: {p}")
        except Exception:
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
    if sys.platform == "win32":
        try:
            import winsound
            winsound.Beep(784, 150)  # G5
            time.sleep(0.04)
            winsound.Beep(1046, 280) # C6
            return
        except Exception:
            pass

    for cmd in [
        "canberra-gtk-play -i message",
        "paplay /usr/share/sounds/freedesktop/stereo/complete.oga",
        "paplay /usr/share/sounds/freedesktop/stereo/bell.oga"
    ]:
        if os.system(f"{cmd} > /dev/null 2>&1") == 0:
            return

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
        self.setStyleSheet("background: rgba(4, 10, 22, 0.85);")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(20, 20, 20, 20)

        self.frame = QFrame()
        self.frame.setFixedSize(700, 390)
        self.frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0b1930, stop:1 #112240);
                border: 2.5px solid #38bdf8;
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
        btn_close_top.clicked.connect(self.close_announcement)
        header.addWidget(btn_close_top)
        frame_layout.addLayout(header)

        self.msg_label = QLabel("")
        self.msg_label.setFont(QFont("Segoe UI", 16, QFont.Weight.DemiBold))
        self.msg_label.setStyleSheet("""
            color: #ffffff;
            background: rgba(7, 16, 32, 0.8);
            border: 1px solid rgba(56, 189, 248, 0.2);
            border-radius: 16px;
            padding: 20px;
            line-height: 1.45;
        """)
        self.msg_label.setWordWrap(True)
        self.msg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(self.msg_label, 1)

        bottom = QHBoxLayout()
        self.lbl_countdown = QLabel("⏱️ 45 saniye sonra kendiliğinden kapanır")
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
        self.setWindowTitle("İdare Duyurusu — Tahta Kilit")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool
        )
        self.setFixedSize(680, 380)
        self.setStyleSheet("background-color: #0b1930; border-radius: 24px;")

        self.duration_left = duration_sec

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.frame = QFrame()
        self.frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0b1930, stop:1 #112240);
                border: 3px solid #38bdf8;
                border-radius: 24px;
            }
        """)
        frame_layout = QVBoxLayout(self.frame)
        frame_layout.setContentsMargins(35, 26, 35, 25)
        frame_layout.setSpacing(16)

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

        msg_label = QLabel(message)
        msg_label.setFont(QFont("Segoe UI", 16, QFont.Weight.DemiBold))
        msg_label.setStyleSheet("""
            color: #ffffff;
            background: rgba(7, 16, 32, 0.78);
            border: 1px solid rgba(56, 189, 248, 0.2);
            border-radius: 16px;
            padding: 20px;
            line-height: 1.45;
        """)
        msg_label.setWordWrap(True)
        msg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(msg_label, 1)

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
# 📢 Mavi Işıklı Gerçek Kayan Bant Bileşeni (LED Marquee Ticker)
# -------------------------------------------------------------
class BlueBannerTicker(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)
        self.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0369a1, stop:0.5 #0284c7, stop:1 #0369a1);
                border-bottom: 2px solid #38bdf8;
            }
        """)

        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(22)
        glow.setColor(QColor(56, 189, 248, 210))
        glow.setOffset(0, 2)
        self.setGraphicsEffect(glow)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(14)

        self.icon_label = QLabel("📢 CANLI İDARE DUYURUSU")
        self.icon_label.setFont(QFont("Segoe UI", 11, QFont.Weight.ExtraBold))
        self.icon_label.setStyleSheet("""
            color: #0f172a;
            background: #fef08a;
            padding: 4px 12px;
            border-radius: 8px;
            border: none;
        """)
        layout.addWidget(self.icon_label)

        self.text_label = QLabel("")
        self.text_label.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.text_label.setStyleSheet("color: #ffffff; background: transparent; border: none;")
        layout.addWidget(self.text_label, 1)

        self.raw_message = ""
        self.scroll_buffer = ""
        self.scroll_pos = 0

        self.timer_scroll = QTimer(self)
        self.timer_scroll.timeout.connect(self._scroll_step)

        self.timer_close = QTimer(self)
        self.timer_close.timeout.connect(self.stop_banner)

        self.hide()

    def show_message(self, message: str, duration_sec: int = 60):
        self.raw_message = message.strip()
        unit = f"   ★ {self.raw_message}   •   "
        self.scroll_buffer = unit * 4
        self.scroll_pos = 0
        self.text_label.setText(self.scroll_buffer[:110])
        self.show()
        self.timer_scroll.start(110)
        self.timer_close.stop()
        self.timer_close.start(duration_sec * 1000)

    def _scroll_step(self):
        if not self.scroll_buffer:
            return
        self.scroll_pos = (self.scroll_pos + 1) % (len(self.scroll_buffer) // 2)
        self.text_label.setText(self.scroll_buffer[self.scroll_pos:self.scroll_pos + 110])

    def stop_banner(self):
        self.timer_scroll.stop()
        self.hide()


# -------------------------------------------------------------
# 🔄 Arka Planda Canlı GitHub Güncelleme İşçisi (Worker Thread)
# İlerleme durumunu, indirme yüzdesini ve hataları canlı yayınlar.
# -------------------------------------------------------------
class UpdateWorkerThread(QThread):
    progress_changed = pyqtSignal(int, str)
    finished_success = pyqtSignal(str)
    failed_error = pyqtSignal(str)

    def run(self):
        import urllib.request
        import json
        import py_compile
        import subprocess

        try:
            # 1. Aşama: GitHub Sürüm Kontrolü (%20)
            self.progress_changed.emit(20, "🌐 GitHub sunucusuna bağlanılıyor...")
            version_url = "https://raw.githubusercontent.com/mercanogretmen-dev/etap-smaart-lock/main/version.json"
            req_ver = urllib.request.Request(version_url, headers={"User-Agent": "TahtaKilitUpdater/1.1"})
            remote_version = "v1.1.1"
            try:
                with urllib.request.urlopen(req_ver, timeout=10) as resp:
                    v_data = json.loads(resp.read().decode("utf-8"))
                    remote_version = v_data.get("version", "v1.1.1")
            except Exception:
                pass

            # 2. Aşama: Yeni Kodları İndirme (%50)
            self.progress_changed.emit(50, f"📥 Yeni sürüm kodları indiriliyor ({remote_version})...")
            code_url = "https://raw.githubusercontent.com/mercanogretmen-dev/etap-smaart-lock/main/client-tahta/kilit_ekrani.py"
            req_code = urllib.request.Request(code_url, headers={"User-Agent": "TahtaKilitUpdater/1.1"})
            with urllib.request.urlopen(req_code, timeout=15) as resp:
                new_code = resp.read()

            if len(new_code) < 30000 or b"class LockScreenWindow" not in new_code:
                raise ValueError("İndirilen güncelleme paketi eksik veya bozuk!")

            # 3. Aşama: Kod Doğrulama (%75)
            self.progress_changed.emit(75, "🔍 Kod güvenliği ve sözdizimi doğrulanıyor...")
            compile(new_code, "<string>", "exec")

            # 4. Aşama: Dosya Yazma (%90)
            self.progress_changed.emit(90, "📁 Sistem dosyaları yenileniyor...")
            target_file = None
            if sys.platform != "win32" and os.path.exists("/opt/etap-smartlock/kilit_ekrani.py"):
                target_file = "/opt/etap-smartlock/kilit_ekrani.py"
            else:
                target_file = os.path.abspath(__file__)

            written = False
            try:
                tmp_target = target_file + ".tmp"
                with open(tmp_target, "wb") as f:
                    f.write(new_code)
                os.replace(tmp_target, target_file)
                written = True
            except PermissionError:
                if sys.platform != "win32":
                    tmp_f = "/tmp/kilit_ekrani_update.py"
                    with open(tmp_f, "wb") as f:
                        f.write(new_code)
                    res = subprocess.run(["pkexec", "cp", tmp_f, target_file], capture_output=True, timeout=20)
                    if res.returncode == 0:
                        written = True
                if not written:
                    raise PermissionError(f"'{target_file}' dizinine doğrudan yazma izni yok! Terminalden 'sudo tahta-kilit-guncelle' çalıştırabilirsiniz.")

            # 5. Aşama: Derleme & Yerel Depo Senkronizasyonu (%98)
            try:
                py_compile.compile(target_file)
            except Exception:
                pass

            for repo_cand in [os.path.expanduser("~/etap-smaart-lock"), os.path.expanduser("~/.etap-smaart-lock"), "/opt/etap-smartlock-repo"]:
                if os.path.isdir(os.path.join(repo_cand, ".git")):
                    try:
                        subprocess.run(["git", "fetch", "origin", "main"], cwd=repo_cand, capture_output=True, timeout=8)
                        subprocess.run(["git", "reset", "--hard", "origin/main"], cwd=repo_cand, capture_output=True, timeout=8)
                    except Exception:
                        pass

            self.progress_changed.emit(100, f"✅ Güncelleme tamamlandı! ({remote_version})")
            self.finished_success.emit(f"Sürüm {remote_version} başarıyla kuruldu! Kilit ekranı yenileniyor...")

        except Exception as e:
            err = str(e)
            if "timed out" in err or "urlopen error" in err:
                err = "İnternet bağlantısı kurulamadı. Lütfen tahtanın internetini kontrol edin."
            self.failed_error.emit(err)


# -------------------------------------------------------------
# ⚙️ Kilit Ekranı İçine Gömülü Ayarlar Katmanı (In-Window Overlay)
# Sınıf Adı, Okul Adı ve Sunucu Adresi hem klavye hem dokunmatikle değiştirilebilir.
# -------------------------------------------------------------
class SettingsOverlayWidget(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.lock_window = parent
        self.active_input = None
        self.init_ui()
        self.hide()

    def init_ui(self):
        self.setStyleSheet("background: rgba(4, 10, 22, 0.88);")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(20, 15, 20, 15)

        card = QFrame()
        card.setFixedSize(740, 625)
        card.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0b1930, stop:1 #0f2240);
                border: 2.5px solid #38bdf8;
                border-radius: 22px;
            }
        """)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(30, 20, 30, 20)
        card_layout.setSpacing(8)

        # Başlık ve Kapat Butonu
        header = QHBoxLayout()
        icon = QLabel("⚙️")
        icon.setFont(QFont("Segoe UI Emoji", 22))
        icon.setStyleSheet("border: none; background: transparent;")
        header.addWidget(icon)

        title = QLabel("TAHTA KİLİT — SİSTEM, OKUL VE SINIF AYARLARI")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.ExtraBold))
        title.setStyleSheet("color: #38bdf8; letter-spacing: 1px; border: none; background: transparent;")
        header.addWidget(title)
        header.addStretch()

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(34, 34)
        btn_close.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        btn_close.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 17px;
            }
            QPushButton:hover { background: #ef4444; color: white; border-color: #ef4444; }
        """)
        btn_close.clicked.connect(self.hide_overlay)
        header.addWidget(btn_close)
        card_layout.addLayout(header)

        # 1. Sınıf / Tahta Adı
        lbl_b = QLabel("🖥️ Sınıf / Tahta Adı (Seçmek için kutuya dokunun veya Tab tuşuna basın):")
        lbl_b.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl_b.setStyleSheet("color: #e2e8f0; border: none; background: transparent;")
        card_layout.addWidget(lbl_b)

        self.input_board = QLineEdit()
        self.input_board.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.input_board.setFixedHeight(40)
        self.input_board.installEventFilter(self)
        card_layout.addWidget(self.input_board)

        # 2. Okul / Kurum Adı
        lbl_s = QLabel("🏫 Okul / Kurum Adı (Üst barda görünür):")
        lbl_s.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl_s.setStyleSheet("color: #e2e8f0; border: none; background: transparent;")
        card_layout.addWidget(lbl_s)

        self.input_school = QLineEdit()
        self.input_school.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
        self.input_school.setFixedHeight(40)
        self.input_school.installEventFilter(self)
        card_layout.addWidget(self.input_school)

        # 3. Sunucu WebSocket URL
        lbl_u = QLabel("🌐 Sunucu WebSocket Adresi:")
        lbl_u.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl_u.setStyleSheet("color: #cbd5e1; border: none; background: transparent;")
        card_layout.addWidget(lbl_u)

        self.input_url = QLineEdit()
        self.input_url.setFont(QFont("Segoe UI", 10))
        self.input_url.setFixedHeight(36)
        self.input_url.installEventFilter(self)
        card_layout.addWidget(self.input_url)

        self.inputs_list = [self.input_board, self.input_school, self.input_url]
        self.active_input = self.input_board
        self._update_input_styles()

        # Dokunmatik Sanal Klavye (Tahta Üzerinde Kolay Sınıf & Okul Adı Yazımı İçin)
        kb_frame = QFrame()
        kb_frame.setStyleSheet("background: rgba(7, 16, 32, 0.82); border: 1px solid #334155; border-radius: 14px; padding: 4px;")
        kb_layout = QVBoxLayout(kb_frame)
        kb_layout.setContentsMargins(8, 6, 8, 6)
        kb_layout.setSpacing(5)

        rows = [
            ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "."],
            ["A", "B", "C", "Ç", "D", "E", "F", "G", "Ğ", "H", "I", "İ"],
            ["J", "K", "L", "M", "N", "O", "Ö", "P", "R", "S", "Ş", "T"],
            ["U", "Ü", "V", "Y", "Z", "/", ":", "_"],
        ]
        for r_idx, r in enumerate(rows):
            row_layout = QHBoxLayout()
            row_layout.setSpacing(4)
            for ch in r:
                b = QPushButton(ch)
                b.setFixedHeight(32)
                b.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                b.setStyleSheet("""
                    QPushButton {
                        background: #1e293b; color: #f8fafc;
                        border: 1px solid #475569; border-radius: 7px;
                    }
                    QPushButton:pressed { background: #38bdf8; color: #0f172a; }
                """)
                b.clicked.connect(lambda _, c=ch: self._append_char(c))
                row_layout.addWidget(b)

            if r_idx == 3:
                btn_space = QPushButton("␣ BOŞLUK")
                btn_space.setFixedHeight(32)
                btn_space.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                btn_space.setStyleSheet("""
                    QPushButton {
                        background: #334155; color: #38bdf8;
                        border: 1px solid #38bdf8; border-radius: 7px;
                    }
                    QPushButton:pressed { background: #38bdf8; color: #0f172a; }
                """)
                btn_space.clicked.connect(lambda: self._append_char(" "))
                row_layout.addWidget(btn_space, 2)

            kb_layout.addLayout(row_layout)

        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        for preset in ["9-A", "9-B", "10-A", "11-A", "12-A"]:
            pb = QPushButton(preset)
            pb.setFixedHeight(32)
            pb.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            pb.setStyleSheet("""
                QPushButton {
                    background: rgba(56, 189, 248, 0.15); color: #38bdf8;
                    border: 1px solid rgba(56, 189, 248, 0.35); border-radius: 7px;
                }
                QPushButton:pressed { background: #38bdf8; color: #0f172a; }
            """)
            pb.clicked.connect(lambda _, p=preset: self.input_board.setText(p))
            action_row.addWidget(pb)

        btn_bs = QPushButton("⌫ Sil")
        btn_bs.setFixedHeight(32)
        btn_bs.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        btn_bs.setStyleSheet("""
            QPushButton { background: #f59e0b; color: #0f172a; border-radius: 7px; border: none; }
            QPushButton:pressed { background: #d97706; }
        """)
        btn_bs.clicked.connect(self._backspace_char)
        action_row.addWidget(btn_bs)

        btn_clr = QPushButton("Temizle")
        btn_clr.setFixedHeight(32)
        btn_clr.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        btn_clr.setStyleSheet("""
            QPushButton { background: #ef4444; color: #ffffff; border-radius: 7px; border: none; }
            QPushButton:pressed { background: #dc2626; }
        """)
        btn_clr.clicked.connect(self._clear_active)
        action_row.addWidget(btn_clr)

        kb_layout.addLayout(action_row)
        card_layout.addWidget(kb_frame)

        # Bilgi Notu & Canlı Durum
        self.lbl_status = QLabel("💡 Not: Sınıf ve okul adı kaydedildiğinde bağlantı kopmadan anında güncellenir.")
        self.lbl_status.setFont(QFont("Segoe UI", 10))
        self.lbl_status.setStyleSheet("color: #94a3b8; border: none; background: transparent;")
        card_layout.addWidget(self.lbl_status)

        # Görsel İlerleme Çubuğu (Güncelleme esnasında gösterilir)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background: #060f1e;
                border: 1px solid #334155;
                border-radius: 6px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #38bdf8);
                border-radius: 5px;
            }
        """)
        self.progress_bar.hide()
        card_layout.addWidget(self.progress_bar)

        # Butonlar
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)

        self.btn_save = QPushButton("💾 Kaydet (Enter)")
        self.btn_save.setFixedHeight(42)
        self.btn_save.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.btn_save.setStyleSheet("""
            QPushButton {
                background: #10b981;
                color: #ffffff;
                border-radius: 12px;
                border: none;
            }
            QPushButton:hover { background: #059669; }
            QPushButton:pressed { background: #047857; }
        """)
        self.btn_save.clicked.connect(self.save_settings)
        btn_box.addWidget(self.btn_save, 2)

        self.btn_update = QPushButton("🔄 Güncelle (GitHub)")
        self.btn_update.setFixedHeight(42)
        self.btn_update.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.btn_update.setStyleSheet("""
            QPushButton {
                background: #2563eb;
                color: #ffffff;
                border-radius: 12px;
                border: none;
            }
            QPushButton:hover { background: #1d4ed8; }
            QPushButton:pressed { background: #1e40af; }
        """)
        self.btn_update.clicked.connect(self.trigger_update)
        btn_box.addWidget(self.btn_update, 2)

        self.btn_cancel = QPushButton("İptal (Esc)")
        self.btn_cancel.setFixedHeight(42)
        self.btn_cancel.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: #cbd5e1;
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.15); color: #fff; }
        """)
        self.btn_cancel.clicked.connect(self.hide_overlay)
        btn_box.addWidget(self.btn_cancel, 1)

        card_layout.addLayout(btn_box)
        layout.addWidget(card)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            if obj in self.inputs_list:
                self.active_input = obj
                self._update_input_styles()
        return super().eventFilter(obj, event)

    def _update_input_styles(self):
        active_css = """
            QLineEdit {
                background: #060f1e;
                color: #ffffff;
                border: 2.5px solid #38bdf8;
                border-radius: 10px;
                padding: 0 14px;
            }
        """
        inactive_css = """
            QLineEdit {
                background: #060f1e;
                color: #94a3b8;
                border: 1.5px solid #334155;
                border-radius: 10px;
                padding: 0 14px;
            }
        """
        for inp in self.inputs_list:
            inp.setStyleSheet(active_css if inp == self.active_input else inactive_css)

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
        if key in (Qt.Key.Key_Tab, Qt.Key.Key_Down):
            idx = self.inputs_list.index(self.active_input) if self.active_input in self.inputs_list else 0
            self.active_input = self.inputs_list[(idx + 1) % len(self.inputs_list)]
            self._update_input_styles()
            return
        if key == Qt.Key.Key_Up:
            idx = self.inputs_list.index(self.active_input) if self.active_input in self.inputs_list else 0
            self.active_input = self.inputs_list[(idx - 1) % len(self.inputs_list)]
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
        self.input_school.setText(self.lock_window.okul_adi)
        self.input_url.setText(self.lock_window.sunucu_url)
        self.active_input = self.input_board
        self._update_input_styles()
        self.lbl_status.setText("💡 Not: Sınıf ve okul adı kaydedildiğinde bağlantı kopmadan anında güncellenir.")
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
        new_school = self.input_school.text().strip() or "T.C. MİLLÎ EĞİTİM BAKANLIĞI — ETKİLEŞİMLİ TAHTA SİSTEMİ"
        new_url = self.input_url.text().strip()
        self.lock_window.apply_new_settings(new_name, new_url, new_school)
        self.lbl_status.setText("✅ Ayarlar başarıyla kaydedildi ve uygulandı!")
        self.lbl_status.setStyleSheet("color: #34d399; font-weight: bold; border: none; background: transparent;")
        QTimer.singleShot(600, self.hide_overlay)

    def trigger_update(self):
        self.btn_update.setEnabled(False)
        self.btn_save.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.progress_bar.show()
        self.progress_bar.setValue(10)
        self.lbl_status.setText("🔄 GitHub ile bağlantı kuruluyor, lütfen bekleyiniz...")
        self.lbl_status.setStyleSheet("color: #38bdf8; font-weight: bold; border: none; background: transparent;")

        self.update_thread = UpdateWorkerThread()
        self.update_thread.progress_changed.connect(self._on_update_progress)
        self.update_thread.finished_success.connect(self._on_update_success)
        self.update_thread.failed_error.connect(self._on_update_error)
        self.update_thread.start()

    def _on_update_progress(self, percent: int, msg: str):
        self.progress_bar.setValue(percent)
        self.lbl_status.setText(msg)

    def _on_update_success(self, msg: str):
        self.progress_bar.setValue(100)
        self.lbl_status.setText(f"🎉 {msg}")
        self.lbl_status.setStyleSheet("color: #34d399; font-weight: bold; border: none; background: transparent;")
        QTimer.singleShot(1800, self._restart_application)

    def _on_update_error(self, err: str):
        self.progress_bar.hide()
        self.btn_update.setEnabled(True)
        self.btn_save.setEnabled(True)
        self.btn_cancel.setEnabled(True)
        self.lbl_status.setText(f"❌ {err}")
        self.lbl_status.setStyleSheet("color: #ef4444; font-weight: bold; border: none; background: transparent;")

    def _restart_application(self):
        self.lock_window.is_locked = False
        try:
            self.lock_window.releaseKeyboard()
        except Exception:
            pass
        if hasattr(QApplication.instance(), "_single_instance_lock"):
            try:
                QApplication.instance()._single_instance_lock.unlock()
            except Exception:
                pass
        QProcess.startDetached(sys.executable, sys.argv)
        QApplication.quit()


# -------------------------------------------------------------
# 🛡️ Kilit Ekranı İçine Gömülü Yönetici Çıkış Katmanı (Ctrl+Shift+Q)
# -------------------------------------------------------------
class AdminExitOverlayWidget(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.lock_window = parent
        self.init_ui()
        self.hide()

    def init_ui(self):
        self.setStyleSheet("background: rgba(4, 10, 22, 0.90);")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(20, 20, 20, 20)

        card = QFrame()
        card.setFixedSize(560, 480)
        card.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1e1b2e, stop:1 #0b1629);
                border: 2.5px solid #ef4444;
                border-radius: 22px;
            }
        """)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 24, 32, 24)
        card_layout.setSpacing(12)

        header = QHBoxLayout()
        icon = QLabel("🛡️")
        icon.setFont(QFont("Segoe UI Emoji", 26))
        icon.setStyleSheet("border: none; background: transparent;")
        header.addWidget(icon)

        title = QLabel("TAHTA KİLİT — YÖNETİCİ ÇIKIŞI")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.ExtraBold))
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
                background: #060f1e;
                color: #ffffff;
                border: 2.5px solid #ef4444;
                border-radius: 12px;
                padding: 0 16px;
                letter-spacing: 4px;
            }
        """)
        card_layout.addWidget(self.input_pwd)

        pad_frame = QFrame()
        pad_frame.setStyleSheet("background: rgba(7, 16, 32, 0.78); border: 1px solid #334155; border-radius: 14px;")
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
# ✨ Özel Vektörel Çizim Bileşenleri (Sıfır Piksel Kırılması & Gerçek Buzlu Cam)
# Qt QSS border-radius kırılmalarını önlemek için QPainter Antialiasing kullanılır.
# -------------------------------------------------------------
class AmbientBackgroundWidget(QWidget):
    """Arka planda modern siber-uzay ışık küreleri (Aurora), devre yolları (Circuit Traces) ve filigran deseni çizer."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._watermark_pix = None
        wm_path = get_asset_path("mercan_robotik_icon.png")
        if os.path.exists(wm_path):
            self._watermark_pix = QPixmap(wm_path)
        # Performans: Desenli arka plan bir kez çizilip önbelleğe alınır.
        # Kenar ışık animasyonu her karede yalnızca bu hazır görüntüyü kopyalar (düşük CPU).
        self._bg_cache = None

    def resizeEvent(self, event):
        self._bg_cache = None
        super().resizeEvent(event)

    def paintEvent(self, event):
        if self._bg_cache is None or self._bg_cache.size() != self.size():
            self._bg_cache = QPixmap(self.size())
            cache_painter = QPainter(self._bg_cache)
            self._paint_scene(cache_painter)
            cache_painter.end()
        painter = QPainter(self)
        painter.drawPixmap(event.rect(), self._bg_cache, event.rect())

    def _paint_scene(self, painter):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        w, h = float(self.width()), float(self.height())

        # 1. Derin Gece Mavisi / Siber Uzay Ana Gradyan
        bg_grad = QLinearGradient(0, 0, w, h)
        bg_grad.setColorAt(0.0, QColor(4, 10, 22))
        bg_grad.setColorAt(0.35, QColor(9, 22, 44))
        bg_grad.setColorAt(0.70, QColor(13, 30, 56))
        bg_grad.setColorAt(1.0, QColor(5, 12, 26))
        painter.fillRect(self.rect(), bg_grad)

        # 2. Yumuşak Aurora Işık Küreleri (Buzlu camın arkasından parlayan derinlik ışıkları)
        orb1 = QRadialGradient(QPointF(w * 0.25, h * 0.50), max(w, h) * 0.42)
        orb1.setColorAt(0.0, QColor(14, 165, 233, 72))
        orb1.setColorAt(0.45, QColor(2, 132, 199, 28))
        orb1.setColorAt(1.0, QColor(14, 165, 233, 0))
        painter.fillRect(self.rect(), orb1)

        orb2 = QRadialGradient(QPointF(w * 0.76, h * 0.48), max(w, h) * 0.40)
        orb2.setColorAt(0.0, QColor(255, 86, 67, 60))
        orb2.setColorAt(0.45, QColor(225, 29, 72, 22))
        orb2.setColorAt(1.0, QColor(255, 86, 67, 0))
        painter.fillRect(self.rect(), orb2)

        orb3 = QRadialGradient(QPointF(w * 0.50, h * 0.16), max(w, h) * 0.32)
        orb3.setColorAt(0.0, QColor(56, 189, 248, 48))
        orb3.setColorAt(1.0, QColor(56, 189, 248, 0))
        painter.fillRect(self.rect(), orb3)

        # 3. Modern Geometrik Teknoloji Ağı (Tech Grid)
        step = 56
        grid_pen = QPen(QColor(125, 211, 252, 14), 1.0)
        painter.setPen(grid_pen)
        for x in range(0, int(w) + step, step):
            painter.drawLine(x, 0, x, int(h))
        for y in range(0, int(h) + step, step):
            painter.drawLine(0, y, int(w), y)

        # Diyagonal Siber Işık Çizgileri (Buzlu cam arkasında kırılma etkisi yaratır)
        diag_pen = QPen(QColor(56, 189, 248, 12), 1.2)
        painter.setPen(diag_pen)
        for offset in range(-int(h), int(w) + int(h), step * 3):
            painter.drawLine(offset, 0, offset + int(h * 0.65), int(h))

        # 4. Siber Devre Yolları (Circuit Traces) — Logodaki devre hatlarıyla uyumlu
        circuit_pen_cyan = QPen(QColor(56, 189, 248, 42), 1.8)
        circuit_pen_coral = QPen(QColor(255, 94, 77, 38), 1.8)
        traces = [
            # Sol üst ve alt devre hatları (Turkuaz)
            (circuit_pen_cyan, [(0, h * 0.18), (w * 0.08, h * 0.18), (w * 0.13, h * 0.25), (w * 0.22, h * 0.25)]),
            (circuit_pen_cyan, [(0, h * 0.82), (w * 0.10, h * 0.82), (w * 0.15, h * 0.74), (w * 0.26, h * 0.74)]),
            (circuit_pen_cyan, [(w * 0.32, h * 0.12), (w * 0.38, h * 0.18), (w * 0.46, h * 0.18)]),
            # Sağ üst ve alt devre hatları (Mercan)
            (circuit_pen_coral, [(w, h * 0.20), (w * 0.91, h * 0.20), (w * 0.86, h * 0.28), (w * 0.76, h * 0.28)]),
            (circuit_pen_coral, [(w, h * 0.80), (w * 0.89, h * 0.80), (w * 0.84, h * 0.72), (w * 0.72, h * 0.72)]),
            (circuit_pen_coral, [(w * 0.66, h * 0.86), (w * 0.60, h * 0.80), (w * 0.52, h * 0.80)]),
        ]
        for pen, pts in traces:
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath()
            path.moveTo(pts[0][0], pts[0][1])
            for px, py in pts[1:]:
                path.lineTo(px, py)
            painter.drawPath(path)
            # Devre uçlarında parlayan halka düğümler
            end_x, end_y = pts[-1]
            painter.setBrush( QColor(10, 23, 44, 220))
            painter.drawEllipse(QPointF(end_x, end_y), 4.5, 4.5)

        # Kesişim noktalarında mikro parıltılar
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(56, 189, 248, 35))
        for x in range(step, int(w), step * 2):
            for y in range(step, int(h), step * 2):
                painter.drawEllipse(QPointF(x, y), 2.0, 2.0)

        # 5. Arka Plan Köşe Filigranı (Buzlu camın altında hafif teknoloji amblemi)
        if self._watermark_pix and not self._watermark_pix.isNull():
            painter.save()
            painter.setOpacity(0.055)
            wm_sz = int(min(w, h) * 0.52)
            scaled_wm = self._watermark_pix.scaled(
                wm_sz, wm_sz,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            painter.drawPixmap(int(w * 0.50 - wm_sz / 2), int(h * 0.50 - wm_sz / 2), scaled_wm)
            painter.restore()


class ArchitecturalBar(QFrame):
    """Üst ve alt bilgi bantları için tam genişlikte, düz (flat) ve modern mimari cam bar."""
    def __init__(self, position="top", parent=None):
        super().__init__(parent)
        self.position = position  # "top" veya "bottom"
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        w, h = float(self.width()), float(self.height())

        # Düz koyu mimari cam dolgu
        bg_grad = QLinearGradient(0, 0, w, 0)
        bg_grad.setColorAt(0.0, QColor(5, 12, 25, 232))
        bg_grad.setColorAt(0.5, QColor(9, 20, 40, 222))
        bg_grad.setColorAt(1.0, QColor(5, 12, 25, 232))
        painter.fillRect(self.rect(), bg_grad)

        # İnce teknolojik sınır çizgisi (Turkuaz -> Gümüş -> Mercan geçişli düz çizgi)
        line_grad = QLinearGradient(0, 0, w, 0)
        line_grad.setColorAt(0.0, QColor(56, 189, 248, 130))
        line_grad.setColorAt(0.5, QColor(255, 255, 255, 55))
        line_grad.setColorAt(1.0, QColor(255, 86, 67, 130))
        painter.setPen(QPen(QBrush(line_grad), 1.2))
        if self.position == "top":
            painter.drawLine(0, int(h) - 1, int(w), int(h) - 1)
        else:
            painter.drawLine(0, 0, int(w), 0)


class VerticalDivider(QWidget):
    """Üst ve alt bardaki bölümleri birbirinden ayıran zarif dikey düz çizgi."""
    def __init__(self, height_px=26, parent=None):
        super().__init__(parent)
        self.setFixedSize(2, height_px)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def paintEvent(self, event):
        painter = QPainter(self)
        h = float(self.height())
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor(148, 163, 184, 0))
        grad.setColorAt(0.5, QColor(148, 163, 184, 90))
        grad.setColorAt(1.0, QColor(148, 163, 184, 0))
        painter.fillRect(QRectF(0.0, 0.0, 1.2, h), grad)


class FlatBarSegment(QLabel):
    """Üst ve alt barda oval çerçeve yerine düz (flat), alt/sol ince ışıklı çizgiye sahip modern bilgi bölümü."""
    def __init__(
        self,
        text="",
        accent_color=QColor(56, 189, 248, 210),
        bg_tint=QColor(56, 189, 248, 20),
        text_color=QColor(241, 245, 249),
        pad_x=12,
        pad_y=5,
        show_bottom_bar=True,
        parent=None
    ):
        super().__init__(text, parent)
        self.accent_color = accent_color
        self.bg_tint = bg_tint
        self.text_color = text_color
        self.show_bottom_bar = show_bottom_bar
        self.setContentsMargins(pad_x, pad_y, pad_x, pad_y)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(f"color: {self.text_color.name()}; background: transparent; border: none;")

    def set_segment_colors(self, accent_color: QColor, bg_tint: QColor, text_color: QColor):
        self.accent_color = accent_color
        self.bg_tint = bg_tint
        self.text_color = text_color
        self.setStyleSheet(f"color: {self.text_color.name()}; background: transparent; border: none;")
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        w, h = float(self.width()), float(self.height())

        if self.bg_tint.alpha() > 0:
            painter.fillRect(QRectF(0, 0, w, h), self.bg_tint)

        if self.show_bottom_bar and self.accent_color.alpha() > 0:
            painter.fillRect(QRectF(0, h - 2.5, w, 2.5), self.accent_color)

        super().paintEvent(event)


class FrostedPillLabel(QLabel):
    """Orta kart içindeki bilgi şeridi için QPainter Antialiasing ile pürüzsüz buzlu cam etiket."""
    def __init__(
        self,
        text="",
        bg_color=QColor(255, 255, 255, 16),
        border_color=QColor(255, 255, 255, 42),
        text_color=QColor(241, 245, 249),
        radius=11.0,
        pad_x=14,
        pad_y=6,
        parent=None
    ):
        super().__init__(text, parent)
        self.bg_color = bg_color
        self.border_color = border_color
        self.text_color = text_color
        self.radius = radius
        self.setContentsMargins(pad_x, pad_y, pad_x, pad_y)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(f"color: {self.text_color.name()}; background: transparent; border: none;")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(1.0, 1.0, self.width() - 2.0, self.height() - 2.0)
        r = min(self.radius, rect.height() / 2.0)
        path = QPainterPath()
        path.addRoundedRect(rect, r, r)
        painter.fillPath(path, self.bg_color)
        painter.setPen(QPen(self.border_color, 1.25))
        painter.drawPath(path)
        super().paintEvent(event)


class FrostedGlassCard(QFrame):
    """Pürüzsüz (Anti-aliased) oval köşeli gerçek Buzlu Cam (Glassmorphism) kart bileşeni."""
    def __init__(self, accent_color=QColor(56, 189, 248, 95), radius=26.0, parent=None):
        super().__init__(parent)
        self.accent_color = accent_color
        self.radius = radius
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRectF(1.5, 1.5, self.width() - 3.0, self.height() - 3.0)
        path = QPainterPath()
        path.addRoundedRect(rect, self.radius, self.radius)

        # Buzlu Cam Yarı Saydam İç Dolgu
        fill_grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        fill_grad.setColorAt(0.0, QColor(255, 255, 255, 24))
        fill_grad.setColorAt(0.35, QColor(20, 38, 68, 145))
        fill_grad.setColorAt(1.0, QColor(9, 20, 38, 175))
        painter.fillPath(path, fill_grad)

        # Üst Cam Yansıma Şeridi (Specular Highlight)
        top_shine_rect = QRectF(rect.left() + 18, rect.top() + 1.0, rect.width() - 36, 1.2)
        shine_grad = QLinearGradient(top_shine_rect.topLeft(), top_shine_rect.topRight())
        shine_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
        shine_grad.setColorAt(0.5, QColor(255, 255, 255, 95))
        shine_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(top_shine_rect, shine_grad)

        # Pürüzsüz Vektörel Cam Kenarlık (Sıfır piksel kırılması)
        border_grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        border_grad.setColorAt(0.0, QColor(255, 255, 255, 68))
        border_grad.setColorAt(0.5, self.accent_color)
        border_grad.setColorAt(1.0, QColor(255, 255, 255, 25))
        painter.setPen(QPen(QBrush(border_grad), 1.5))
        painter.drawPath(path)



class SmoothQrFrame(QFrame):
    """QR Kod için pürüzsüz anti-aliased yuvarlak köşeli beyaz kart."""
    def __init__(self, radius=22.0, parent=None):
        super().__init__(parent)
        self.radius = radius
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(2.0, 2.0, self.width() - 4.0, self.height() - 4.0)
        path = QPainterPath()
        path.addRoundedRect(rect, self.radius, self.radius)
        painter.fillPath(path, QColor(255, 255, 255, 252))
        painter.setPen(QPen(QColor(56, 189, 248, 150), 2.0))
        painter.drawPath(path)


class FrostedPinCapsule(QLabel):
    """PIN noktalarını veya uyarı mesajını pürüzsüz buzlu cam kapsül içinde vektörel çizer."""
    def __init__(self, text="○ ○ ○ ○", parent=None):
        super().__init__(text, parent)
        self.mode = "normal"
        self.pin_length = 0
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def set_mode_and_length(self, mode: str, pin_length: int):
        self.mode = mode
        self.pin_length = pin_length
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        rect = QRectF(1.5, 1.5, self.width() - 3.0, self.height() - 3.0)
        radius = rect.height() / 2.0
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        if self.mode == "error":
            painter.fillPath(path, QColor(127, 29, 29, 110))
            painter.setPen(QPen(QColor(248, 113, 113, 190), 1.6))
        elif self.mode == "active":
            painter.fillPath(path, QColor(8, 18, 36, 155))
            painter.setPen(QPen(QColor(56, 189, 248, 160), 1.5))
        else:
            painter.fillPath(path, QColor(8, 18, 36, 130))
            painter.setPen(QPen(QColor(255, 255, 255, 45), 1.3))
        painter.drawPath(path)

        txt = self.text()
        if "○" in txt or "●" in txt:
            total_dots = max(4, self.pin_length)
            spacing = 32.0 if self.width() > 300 else 28.0
            total_w = (total_dots - 1) * spacing
            start_x = self.width() / 2.0 - total_w / 2.0
            cy = self.height() / 2.0

            for i in range(total_dots):
                cx = start_x + i * spacing
                if i < self.pin_length:
                    # Yanan parlak mavi/mercan nokta
                    glow = QRadialGradient(QPointF(cx, cy), 12.0)
                    glow.setColorAt(0.0, QColor(56, 189, 248, 255))
                    glow.setColorAt(0.65, QColor(56, 189, 248, 190))
                    glow.setColorAt(1.0, QColor(56, 189, 248, 0))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(glow)
                    painter.drawEllipse(QPointF(cx, cy), 12.0, 12.0)

                    painter.setBrush(QColor(240, 249, 255))
                    painter.drawEllipse(QPointF(cx, cy), 5.8, 5.8)
                else:
                    # Boş buzlu cam halka
                    painter.setBrush(QColor(255, 255, 255, 15))
                    painter.setPen(QPen(QColor(148, 163, 184, 125), 1.6))
                    painter.drawEllipse(QPointF(cx, cy), 5.8, 5.8)
        else:
            painter.setPen(QColor(252, 165, 165) if self.mode == "error" else QColor(248, 250, 252))
            painter.setFont(QFont("DejaVu Sans", 14, QFont.Weight.ExtraBold))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, txt)


class FrostedGlassButton(QPushButton):
    """Gerçek Buzlu Cam (Frosted Glass) dokunmatik tuş bileşeni — cep telefonu tuş takımı oranlarında ve sıfır piksel kırılmalı."""
    def __init__(self, text: str, variant: str = "number", font_pt: int = 23, parent=None):
        super().__init__(text, parent)
        self.variant = variant  # "number", "clear", "unlock", "header"
        self.font_pt = font_pt
        self.hovered = False
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def enterEvent(self, event):
        self.hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        rect = QRectF(1.5, 1.5, self.width() - 3.0, self.height() - 3.0)
        if self.variant == "header":
            radius = 5.0
        else:
            # Cep telefonu arama tuş takımı (Phone Dialer) oranlarında yumuşak kavis
            radius = min(rect.width(), rect.height()) * 0.35
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        pressed = self.isDown()

        # Buzlu Cam Dolgu & İnce Cam Kenarlık
        fill_grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        if self.variant == "unlock":
            if pressed:
                fill_grad.setColorAt(0.0, QColor(16, 185, 129, 140))
                fill_grad.setColorAt(1.0, QColor(5, 150, 105, 160))
            elif self.hovered:
                fill_grad.setColorAt(0.0, QColor(52, 211, 153, 90))
                fill_grad.setColorAt(1.0, QColor(16, 185, 129, 60))
            else:
                fill_grad.setColorAt(0.0, QColor(52, 211, 153, 58))
                fill_grad.setColorAt(1.0, QColor(16, 185, 129, 32))
            border_color = QColor(110, 231, 183, 140 if self.hovered else 105)
            text_color = QColor(236, 253, 245)
        elif self.variant == "clear":
            if pressed:
                fill_grad.setColorAt(0.0, QColor(244, 63, 94, 140))
                fill_grad.setColorAt(1.0, QColor(225, 29, 72, 160))
            elif self.hovered:
                fill_grad.setColorAt(0.0, QColor(251, 113, 133, 88))
                fill_grad.setColorAt(1.0, QColor(244, 63, 94, 56))
            else:
                fill_grad.setColorAt(0.0, QColor(255, 94, 77, 54))
                fill_grad.setColorAt(1.0, QColor(225, 29, 72, 30))
            border_color = QColor(253, 164, 175, 135 if self.hovered else 98)
            text_color = QColor(255, 241, 242)
        elif self.variant == "header":
            if pressed or self.hovered:
                fill_grad.setColorAt(0.0, QColor(56, 189, 248, 48))
                fill_grad.setColorAt(1.0, QColor(14, 165, 233, 28))
                border_color = QColor(125, 211, 252, 110)
            else:
                fill_grad.setColorAt(0.0, QColor(255, 255, 255, 14))
                fill_grad.setColorAt(1.0, QColor(255, 255, 255, 6))
                border_color = QColor(255, 255, 255, 36)
            text_color = QColor(226, 232, 240)
        else:
            if pressed:
                fill_grad.setColorAt(0.0, QColor(56, 189, 248, 120))
                fill_grad.setColorAt(1.0, QColor(14, 165, 233, 85))
                border_color = QColor(125, 211, 252, 190)
            elif self.hovered:
                fill_grad.setColorAt(0.0, QColor(255, 255, 255, 48))
                fill_grad.setColorAt(1.0, QColor(56, 189, 248, 28))
                border_color = QColor(125, 211, 252, 130)
            else:
                fill_grad.setColorAt(0.0, QColor(255, 255, 255, 28))
                fill_grad.setColorAt(1.0, QColor(255, 255, 255, 11))
                border_color = QColor(255, 255, 255, 62)
            text_color = QColor(248, 250, 252)

        painter.fillPath(path, fill_grad)

        # Üst İnce Cam Parıltısı
        shine = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        shine.setColorAt(0.0, border_color)
        shine.setColorAt(1.0, QColor(border_color.red(), border_color.green(), border_color.blue(), 26))
        painter.setPen(QPen(QBrush(shine), 1.35))
        painter.drawPath(path)

        # Metin Çizimi
        painter.setPen(text_color)
        weight = QFont.Weight.Bold
        painter.setFont(QFont("DejaVu Sans", self.font_pt, weight))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())


# -------------------------------------------------------------
# 🔒 Ana Kilit Ekranı Penceresi (TAHTA KİLİT v1.1 Modern Kiosk)
# -------------------------------------------------------------
class LockScreenWindow(QMainWindow):
    QUOTES = [
        '💡 "Hayatta en hakiki mürşit ilimdir, fendir." — M. Kemal Atatürk',
        '💡 "Eğitimdir ki, bir milleti ya özgür, bağımsız, şanlı, yüksek bir topluluk halinde yaşatır..." — M. Kemal Atatürk',
        '💡 "Bilim ve teknoloji, geleceği inşa eden en güçlü anahtardır." — Mercan Robotik',
        '💡 "Bir ulusun çağdaş ülkeler düzeyine erişebilmesi; eğitim ve öğretimin kaliteli ve bilimsel yöntemlerle yürütülmesi ile ancak mümkün olabilir."',
    ]

    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.cihaz_id = get_device_id(self.cfg)
        self.sinif_adi = self.cfg.get("GENEL", "sinif_adi", fallback="9-A")
        self.okul_adi = self.cfg.get("GENEL", "okul_adi", fallback="T.C. MİLLÎ EĞİTİM BAKANLIĞI — ETKİLEŞİMLİ TAHTA SİSTEMİ")
        self.sunucu_url = self.cfg.get("GENEL", "sunucu_ws_url", fallback="wss://etap-smaart-lock.onrender.com/ws/board/")
        self.ogretmen_pin = self.cfg.get("GENEL", "ogretmen_pin", fallback="1234")
        self.yonetici_sifre = self.cfg.get("GENEL", "yonetici_sifre", fallback="admin123")

        self.entered_pin = ""
        self.is_locked = True
        self.qr_seconds_left = 30
        self.quote_index = 0

        self.announcement_overlay = None
        self.settings_overlay = None
        self.admin_exit_overlay = None
        self.desktop_announcement_dlg = None

        self.init_ui()
        self.init_network()
        self.setup_kiosk_security()

    def init_ui(self):
        self.setWindowTitle(f"{APP_NAME} — {DEVELOPER_NAME}")
        icon_path = get_asset_path("tahta_kilit_icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # Tam Ekran Kiosk Pencere Özellikleri (Windows+D & görev çubuğu korumalı)
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.BypassWindowManagerHint
        )
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        # Ekran boyutuna göre duyarlı (responsive) ölçekleme:
        # Hem 1280x720 / 1366x768 sanal makine ekranlarına hem de 1920x1080 akıllı tahtaya tam sığar!
        screen = QApplication.primaryScreen()
        sw = screen.geometry().width() if screen else 1920
        sh = screen.geometry().height() if screen else 1080
        compact = (sw < 1500 or sh < 860)

        top_bar_h = 56 if compact else 68
        footer_h = 44 if compact else 52
        body_margin_x = 24 if compact else 50
        body_margin_y = 14 if compact else 24
        body_spacing = 22 if compact else 40
        qr_box_size = 188 if compact else 228
        clock_pt = 34 if compact else 44
        # Kompakt ve zarif numaratör butonları (Kullanıcı isteğiyle küçültüldü)
        numpad_w = 78 if compact else 90
        numpad_h = 50 if compact else 58
        numpad_spacing_x = 10 if compact else 14
        numpad_spacing_y = 8 if compact else 12
        logo_w = 205 if compact else 245
        logo_h = 54 if compact else 66

        # Ana Düzen — Ambiyans Işık Küreleri (Aurora) ve Geometrik Teknoloji Desenli Arka Plan
        main_widget = AmbientBackgroundWidget()
        main_widget.setObjectName("MainRoot")
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # -------------------------------------------------------------
        # 1. En Üst: Mavi Işıklı Gerçek Kayan Duyuru Bandı (LED Ticker)
        # -------------------------------------------------------------
        self.banner = BlueBannerTicker(self)
        main_layout.addWidget(self.banner)

        # -------------------------------------------------------------
        # 2. Üst Kurumsal Bar: Oval çerçevesiz, düz (Flat Architectural HUD) ve dikey ayraçlı modern tasarım
        # -------------------------------------------------------------
        top_bar = ArchitecturalBar(position="top")
        top_bar.setFixedHeight(top_bar_h)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(18 if compact else 28, 0, 18 if compact else 28, 0)
        top_layout.setSpacing(12 if compact else 16)

        # Sol: Tahta Kilit Amblemi + Marka Başlığı
        icon_dim = 38 if compact else 44
        self.lbl_app_icon = QLabel()
        self.lbl_app_icon.setFixedSize(icon_dim, icon_dim)
        self.lbl_app_icon.setStyleSheet("border: none; background: transparent;")
        if os.path.exists(icon_path):
            self.lbl_app_icon.setPixmap(
                QPixmap(icon_path).scaled(
                    icon_dim, icon_dim,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
            )
        top_layout.addWidget(self.lbl_app_icon)

        brand_col = QVBoxLayout()
        brand_col.setSpacing(0)
        brand_col.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        lbl_brand_title = QLabel("TAHTA <span style='color:#ff5643;'>KİLİT</span>")
        lbl_brand_title.setFont(QFont("DejaVu Sans", 13 if compact else 15, QFont.Weight.ExtraBold))
        lbl_brand_title.setStyleSheet("color: #f8fafc; letter-spacing: 0.8px; border: none; background: transparent;")
        lbl_brand_sub = QLabel("ETKİLEŞİMLİ TAHTA KİLİT")
        lbl_brand_sub.setFont(QFont("DejaVu Sans", 7 if compact else 8, QFont.Weight.Bold))
        lbl_brand_sub.setStyleSheet("color: #94a3b8; letter-spacing: 0.5px; border: none; background: transparent;")
        brand_col.addWidget(lbl_brand_title)
        brand_col.addWidget(lbl_brand_sub)
        top_layout.addLayout(brand_col)

        top_layout.addWidget(VerticalDivider(height_px=28 if compact else 34))

        # Sınıf Bölümü (Oval kutu yerine düz mimari şerit + alt turkuaz vurgu çizgisi)
        self.lbl_class = FlatBarSegment(
            f"🖥️ {self.sinif_adi}",
            accent_color=QColor(56, 189, 248, 230),
            bg_tint=QColor(56, 189, 248, 22),
            text_color=QColor(255, 255, 255),
            pad_x=14,
            pad_y=8,
            show_bottom_bar=True
        )
        self.lbl_class.setFont(QFont("DejaVu Sans", 13 if compact else 15, QFont.Weight.ExtraBold))
        top_layout.addWidget(self.lbl_class)

        top_layout.addWidget(VerticalDivider(height_px=28 if compact else 34))

        # Orta: Kurumsal Okul Adı (Tamamen çerçevesiz, düz ve ferah tipografi)
        self.lbl_school = QLabel(f"🏫  {self.okul_adi}")
        self.lbl_school.setFont(QFont("DejaVu Sans", 10 if compact else 11, QFont.Weight.Bold))
        self.lbl_school.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_school.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.lbl_school.setMinimumWidth(140)
        self.lbl_school.setStyleSheet("color: #f1f5f9; letter-spacing: 0.4px; border: none; background: transparent;")
        top_layout.addWidget(self.lbl_school, 1)

        top_layout.addWidget(VerticalDivider(height_px=28 if compact else 34))

        # Sağ: Cihaz ID (Düz, çerçevesiz teknik etiket)
        lbl_dev = QLabel(f"🆔 {self.cihaz_id}")
        lbl_dev.setFont(QFont("DejaVu Sans", 9 if compact else 10, QFont.Weight.Bold))
        lbl_dev.setStyleSheet("color: #94a3b8; border: none; background: transparent; padding: 0 4px;")
        top_layout.addWidget(lbl_dev)

        top_layout.addWidget(VerticalDivider(height_px=28 if compact else 34))

        # Bağlantı Durumu (Düz mimari gösterge + alt durum şeridi)
        self.lbl_status = FlatBarSegment(
            "● Çevrimdışı (PIN)",
            accent_color=QColor(248, 113, 113, 220),
            bg_tint=QColor(239, 68, 68, 22),
            text_color=QColor(252, 165, 165),
            pad_x=12,
            pad_y=8,
            show_bottom_bar=True
        )
        self.lbl_status.setFont(QFont("DejaVu Sans", 10 if compact else 11, QFont.Weight.Bold))
        top_layout.addWidget(self.lbl_status)

        btn_settings = FrostedGlassButton("⚙️", variant="header", font_pt=13 if compact else 14)
        btn_settings.setFixedSize(36 if compact else 40, 36 if compact else 40)
        btn_settings.clicked.connect(self.open_settings)
        top_layout.addWidget(btn_settings)

        main_layout.addWidget(top_bar)

        # -------------------------------------------------------------
        # 3. Orta Gövde: İki Pürüzsüz Vektörel Buzlu Cam Kart (FrostedGlassCard)
        # Oval köşeler QPainter Antialiasing ile çizildiği için piksel kırılması %0'dır!
        # -------------------------------------------------------------
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(body_margin_x, body_margin_y, body_margin_x, body_margin_y)
        body_layout.setSpacing(body_spacing)

        # === SOL BUZLU CAM KART (Dijital Saat, Tarih, Logolu QR Kod & Canlı Geri Sayım Çubuğu) ===
        left_card = FrostedGlassCard(accent_color=QColor(56, 189, 248, 95), radius=26.0)

        left_box = QVBoxLayout(left_card)
        left_box.setContentsMargins(24, 16 if compact else 24, 24, 16 if compact else 24)
        left_box.setSpacing(6 if compact else 10)
        left_box.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Dijital Saat
        self.lbl_clock = QLabel("10:00:00")
        self.lbl_clock.setFont(QFont("DejaVu Sans", clock_pt, QFont.Weight.ExtraBold))
        self.lbl_clock.setStyleSheet("color: #ffffff; letter-spacing: 2px; border: none; background: transparent;")
        left_box.addWidget(self.lbl_clock, alignment=Qt.AlignmentFlag.AlignCenter)

        # Tarih
        self.lbl_date = QLabel("8 Kasım 2026, Pazar")
        self.lbl_date.setFont(QFont("DejaVu Sans", 12 if compact else 14, QFont.Weight.Bold))
        self.lbl_date.setStyleSheet("color: #7dd3fc; margin-bottom: 4px; border: none; background: transparent;")
        left_box.addWidget(self.lbl_date, alignment=Qt.AlignmentFlag.AlignCenter)

        # QR Kod Pürüzsüz Çerçevesi (SmoothQrFrame)
        qr_frame = SmoothQrFrame(radius=22.0)
        qr_frame.setFixedSize(qr_box_size + 22, qr_box_size + 22)
        qr_layout = QVBoxLayout(qr_frame)
        qr_layout.setContentsMargins(11, 11, 11, 11)
        self.qr_display_size = qr_box_size
        self.lbl_qr = QLabel()
        self.lbl_qr.setFixedSize(qr_box_size, qr_box_size)
        self.lbl_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_qr.setStyleSheet("border: none; background: transparent;")
        qr_layout.addWidget(self.lbl_qr)
        left_box.addWidget(qr_frame, alignment=Qt.AlignmentFlag.AlignCenter)

        # QR Kod Canlı 30 Sn İlerleme Çubuğu (Progress Bar)
        self.qr_progress = QProgressBar()
        self.qr_progress.setRange(0, 30)
        self.qr_progress.setValue(30)
        self.qr_progress.setTextVisible(False)
        self.qr_progress.setFixedSize(qr_box_size + 22, 7)
        self.qr_progress.setStyleSheet("""
            QProgressBar {
                background-color: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #38bdf8, stop:1 #ff5643);
                border-radius: 3px;
            }
        """)
        left_box.addWidget(self.qr_progress, alignment=Qt.AlignmentFlag.AlignCenter)

        self.lbl_qr_timer = QLabel("🔄 Güvenlik QR kodu 30 sn içinde yenilenecek")
        self.lbl_qr_timer.setFont(QFont("DejaVu Sans", 9 if compact else 10, QFont.Weight.DemiBold))
        self.lbl_qr_timer.setStyleSheet("color: #cbd5e1; border: none; background: transparent;")
        left_box.addWidget(self.lbl_qr_timer, alignment=Qt.AlignmentFlag.AlignCenter)

        qr_hint = FrostedPillLabel(
            "📱 Tahta Kilit Mobil Uygulaması ile Okutun",
            bg_color=QColor(56, 189, 248, 36),
            border_color=QColor(125, 211, 252, 95),
            text_color=QColor(224, 242, 254),
            radius=13.0,
            pad_x=16,
            pad_y=5
        )
        qr_hint.setFont(QFont("DejaVu Sans", 10 if compact else 11, QFont.Weight.Bold))
        left_box.addWidget(qr_hint, alignment=Qt.AlignmentFlag.AlignCenter)

        body_layout.addWidget(left_card, 1)

        # === SAĞ BUZLU CAM KART (Yeni Tahta Kilit Logosu + Vektörel PIN Kapsülü + Cep Telefonu Oranlı Tuş Takımı) ===
        right_card = FrostedGlassCard(accent_color=QColor(255, 94, 77, 90), radius=26.0)

        right_box = QVBoxLayout(right_card)
        right_box.setContentsMargins(26, 16 if compact else 24, 26, 16 if compact else 24)
        right_box.setSpacing(0)
        right_box.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Yeni Şeffaf Tahta Kilit Tipografi Logosu ("Interactive Board Lock" kaldırıldı)
        logo_banner_path = get_asset_path("tahta_kilit_logo.png")
        if os.path.exists(logo_banner_path):
            lbl_tk_logo = QLabel()
            lbl_tk_logo.setFixedSize(logo_w, logo_h)
            lbl_tk_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_tk_logo.setStyleSheet("border: none; background: transparent;")
            lbl_tk_logo.setPixmap(
                QPixmap(logo_banner_path).scaled(
                    logo_w, logo_h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
            )
            right_box.addWidget(lbl_tk_logo, alignment=Qt.AlignmentFlag.AlignCenter)
        else:
            pin_title = QLabel("TAHTA KİLİT")
            pin_title.setFont(QFont("DejaVu Sans", 16, QFont.Weight.ExtraBold))
            pin_title.setStyleSheet("color: #f1f5f9; border: none; background: transparent;")
            right_box.addWidget(pin_title, alignment=Qt.AlignmentFlag.AlignCenter)

        # 1. Ferah Ayrım: Logo ile PIN alanı arası
        right_box.addSpacing(14 if compact else 20)

        pin_desc = QLabel("PIN GİRİNİZ")
        pin_desc.setFont(QFont("DejaVu Sans", 10 if compact else 11, QFont.Weight.Bold))
        pin_desc.setStyleSheet("color: #94a3b8; letter-spacing: 2px; border: none; background: transparent;")
        right_box.addWidget(pin_desc, alignment=Qt.AlignmentFlag.AlignCenter)

        # 2. Küçük Ayrım: Başlık ile Kapsül arası
        right_box.addSpacing(8 if compact else 11)

        # Pürüzsüz Buzlu Cam PIN Kapsülü (FrostedPinCapsule)
        pin_w = numpad_w * 3 + numpad_spacing_x * 2
        self.pin_display = FrostedPinCapsule("○ ○ ○ ○")
        self.pin_display.setFixedSize(pin_w, 42 if compact else 48)
        self.pin_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_pin_display_style("normal")
        right_box.addWidget(self.pin_display, alignment=Qt.AlignmentFlag.AlignCenter)

        # 3. Belirgin ve Estetik Ayrım: Giriş Kapsülü ile Tuş Takımı arası
        right_box.addSpacing(16 if compact else 22)

        # Cep Telefonu Arama Görünümü (Phone Dialer) Oranlarında Kompakt Buzlu Cam Tuş Takımı
        numpad_grid = QGridLayout()
        numpad_grid.setHorizontalSpacing(numpad_spacing_x)
        numpad_grid.setVerticalSpacing(numpad_spacing_y)

        buttons = [
            ("1", 0, 0), ("2", 0, 1), ("3", 0, 2),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
            ("7", 2, 0), ("8", 2, 1), ("9", 2, 2),
            ("SİL", 3, 0), ("0", 3, 1), ("AÇ ✓", 3, 2),
        ]

        for text, row, col in buttons:
            if text == "AÇ ✓":
                btn = FrostedGlassButton(text, variant="unlock", font_pt=12 if compact else 14)
                btn.clicked.connect(self.verify_pin)
            elif text == "SİL":
                btn = FrostedGlassButton(text, variant="clear", font_pt=12 if compact else 14)
                btn.clicked.connect(self.clear_pin)
            else:
                btn = FrostedGlassButton(text, variant="number", font_pt=19 if compact else 22)
                btn.clicked.connect(lambda _, t=text: self.append_pin(t))

            btn.setFixedSize(numpad_w, numpad_h)
            numpad_grid.addWidget(btn, row, col)

        right_box.addLayout(numpad_grid)
        body_layout.addWidget(right_card, 1)

        main_layout.addWidget(body, 1)

        # -------------------------------------------------------------
        # 4. Alt Bilgi Bandı (Footer): Oval çerçevesiz, düz (Flat Architectural) ve dikey ayraçlı modern alt bar
        # -------------------------------------------------------------
        footer_bar = ArchitecturalBar(position="bottom")
        footer_bar.setFixedHeight(footer_h)
        footer_layout = QHBoxLayout(footer_bar)
        footer_layout.setContentsMargins(18 if compact else 28, 0, 18 if compact else 28, 0)
        footer_layout.setSpacing(12 if compact else 16)

        # Sol: Günün Sözü (Esnek boyut — ekranı asla sağa doğru taşırmaz!)
        self.lbl_quote = QLabel(self.QUOTES[0])
        self.lbl_quote.setFont(QFont("DejaVu Sans", 9 if compact else 10, QFont.Weight.DemiBold))
        self.lbl_quote.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.lbl_quote.setMinimumWidth(120)
        self.lbl_quote.setStyleSheet("color: #cbd5e1; border: none; background: transparent;")
        footer_layout.addWidget(self.lbl_quote, 1)

        footer_layout.addWidget(VerticalDivider(height_px=24 if compact else 28))

        # Orta-Sağ: Geliştirici MERCAN ROBOTİK Amblemi & Kimliği (Düz, çerçevesiz mimari görünüm)
        dev_badge = QWidget()
        dev_badge.setStyleSheet("background: transparent; border: none;")
        dev_layout = QHBoxLayout(dev_badge)
        dev_layout.setContentsMargins(4, 0, 4, 0)
        dev_layout.setSpacing(7)

        mr_icon_path = get_asset_path("mercan_robotik_icon.png")
        mr_dim = 26 if compact else 30
        if os.path.exists(mr_icon_path):
            lbl_mr_icon = QLabel()
            lbl_mr_icon.setFixedSize(mr_dim, mr_dim)
            lbl_mr_icon.setStyleSheet("border: none; background: transparent;")
            lbl_mr_icon.setPixmap(
                QPixmap(mr_icon_path).scaled(
                    mr_dim, mr_dim,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
            )
            dev_layout.addWidget(lbl_mr_icon)

        lbl_dev_brand = QLabel("Geliştirici: <b style='color:#38bdf8;'>MERCAN</b> <b style='color:#ff5643;'>ROBOTİK</b>")
        lbl_dev_brand.setFont(QFont("DejaVu Sans", 9 if compact else 10))
        lbl_dev_brand.setStyleSheet("color: #e2e8f0; border: none; background: transparent;")
        dev_layout.addWidget(lbl_dev_brand)
        footer_layout.addWidget(dev_badge)

        footer_layout.addWidget(VerticalDivider(height_px=24 if compact else 28))

        # Sağ: 🛡️ ET Güvenliği Aktif ve v1.1 Sürüm Bölümü (Oval kutu yerine düz mimari şerit)
        self.lbl_et_security = FlatBarSegment(
            "🛡️ ET Güvenliği Aktif",
            accent_color=QColor(52, 211, 153, 210),
            bg_tint=QColor(16, 185, 129, 20),
            text_color=QColor(110, 231, 183),
            pad_x=10,
            pad_y=6,
            show_bottom_bar=True
        )
        self.lbl_et_security.setFont(QFont("DejaVu Sans", 9 if compact else 10, QFont.Weight.ExtraBold))
        footer_layout.addWidget(self.lbl_et_security)

        footer_layout.addWidget(VerticalDivider(height_px=24 if compact else 28))

        lbl_version = FlatBarSegment(
            APP_VERSION,
            accent_color=QColor(56, 189, 248, 210),
            bg_tint=QColor(56, 189, 248, 18),
            text_color=QColor(125, 211, 252),
            pad_x=10,
            pad_y=6,
            show_bottom_bar=True
        )
        lbl_version.setFont(QFont("DejaVu Sans", 9 if compact else 10, QFont.Weight.ExtraBold))
        footer_layout.addWidget(lbl_version)

        main_layout.addWidget(footer_bar)

        # -------------------------------------------------------------
        # 5. Zamanlayıcılar (Saat, QR Geri Sayım ve Günün Sözü)
        # -------------------------------------------------------------
        self.timer_clock = QTimer(self)
        self.timer_clock.timeout.connect(self.update_clock_and_qr_countdown)
        self.timer_clock.start(1000)
        self.update_clock()

        self.generate_qr()

        # 6. Kilit Ekranına Gömülü Katmanlar (Asla arkada açılmaz ve görev çubuğunu tetiklemez!)
        self.announcement_overlay = AnnouncementOverlayWidget(self)
        self.announcement_overlay.hide()

        self.settings_overlay = SettingsOverlayWidget(self)
        self.settings_overlay.hide()

        self.admin_exit_overlay = AdminExitOverlayWidget(self)
        self.admin_exit_overlay.hide()

    def _set_pin_display_style(self, mode: str = "normal"):
        if hasattr(self, "pin_display") and isinstance(self.pin_display, FrostedPinCapsule):
            self.pin_display.set_mode_and_length(mode, len(self.entered_pin))

    # -------------------------------------------------------------
    # 🛡️ Kiosk Modu & Öğrenci Güvenlik Koruması (ET Güvenliği)
    # -------------------------------------------------------------
    def setup_kiosk_security(self):
        """Pardus ETAP üzerinde öğrencilerin kilit ekranını aşmasını engelleyen güvenlik koruması."""
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
        """Tam ekran kiosk modunu ekran çözünürlüğüne birebir sığacak şekilde başlatır ve klavyeyi kilitler."""
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.geometry()
            self.setFixedSize(geo.width(), geo.height())
            self.setGeometry(geo)
            self.move(geo.x(), geo.y())
        self.show()
        self.raise_()
        self.activateWindow()
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

    def _fit_school_label_font(self):
        if not hasattr(self, "lbl_school") or not self.lbl_school:
            return
        avail_w = max(160, self.lbl_school.width() - 28)
        text = self.lbl_school.text()
        for pt in [12, 11, 10, 9, 8]:
            f = QFont("DejaVu Sans", pt, QFont.Weight.Bold)
            from PyQt6.QtGui import QFontMetrics
            if QFontMetrics(f).horizontalAdvance(text) <= avail_w:
                self.lbl_school.setFont(f)
                return
        self.lbl_school.setFont(QFont("DejaVu Sans", 8, QFont.Weight.Bold))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_school_label_font()
        for overlay in [
            getattr(self, "announcement_overlay", None),
            getattr(self, "settings_overlay", None),
            getattr(self, "admin_exit_overlay", None)
        ]:
            if overlay:
                overlay.setGeometry(0, 0, self.width(), self.height())

    # -------------------------------------------------------------
    # 🕒 Saat, Canlı QR Geri Sayım & Logolu Dinamik QR Kod
    # -------------------------------------------------------------
    def update_clock(self):
        now = datetime.now()
        self.lbl_clock.setText(now.strftime("%H:%M:%S"))
        gunler = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
        aylar = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
        gun_str = gunler[now.weekday()]
        ay_str = aylar[now.month - 1]
        self.lbl_date.setText(f"{now.day} {ay_str} {now.year}, {gun_str}")

    def update_clock_and_qr_countdown(self):
        self.update_clock()
        self.qr_seconds_left -= 1
        if self.qr_seconds_left <= 0:
            self.generate_qr()
            self.qr_seconds_left = 30
            # Her 30 saniyede bir alt bardaki özdeyişi de sıradakiyle değiştir
            self.quote_index = (self.quote_index + 1) % len(self.QUOTES)
            self.lbl_quote.setText(self.QUOTES[self.quote_index])

        self.qr_progress.setValue(self.qr_seconds_left)
        self.lbl_qr_timer.setText(f"🔄 Güvenlik QR kodu {self.qr_seconds_left} sn içinde yenilenecek")

    def generate_qr(self):
        import urllib.parse
        encoded_name = urllib.parse.quote(self.sinif_adi)
        qr_content = f"etap://unlock?board={self.cihaz_id}&name={encoded_name}&t={int(time.time())}"

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=8,
            border=2,
        )
        qr.add_data(qr_content)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#09152b", back_color="white").convert("RGBA")

        # QR kodun tam ortasına küçük Tahta Kilit amblemini yerleştir
        icon_path = get_asset_path("tahta_kilit_icon.png")
        if os.path.exists(icon_path):
            try:
                logo = Image.open(icon_path).convert("RGBA")
                qr_w, qr_h = img.size
                logo_size = int(qr_w * 0.22)
                logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
                # Beyaz çerçeveli altlık
                pad = 6
                bg_box = Image.new("RGBA", (logo_size + pad * 2, logo_size + pad * 2), (255, 255, 255, 255))
                pos_bg = ((qr_w - bg_box.width) // 2, (qr_h - bg_box.height) // 2)
                pos_logo = ((qr_w - logo_size) // 2, (qr_h - logo_size) // 2)
                img.paste(bg_box, pos_bg)
                img.paste(logo, pos_logo, logo)
            except Exception:
                pass

        data = img.tobytes("raw", "RGBA")
        qim = QImage(data, img.size[0], img.size[1], QImage.Format.Format_RGBA8888)
        target_sz = getattr(self, "qr_display_size", 215)
        self.lbl_qr.setPixmap(
            QPixmap.fromImage(qim).scaled(
                target_sz, target_sz,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        )

    # -------------------------------------------------------------
    # 🔢 PIN Numpad İşlemleri
    # -------------------------------------------------------------
    def _format_pin_dots(self) -> str:
        n = len(self.entered_pin)
        if n == 0:
            return "○ ○ ○ ○"
        if n <= 4:
            return " ".join(["●"] * n + ["○"] * (4 - n))
        return " ".join(["●"] * n)

    def append_pin(self, digit: str):
        if len(self.entered_pin) < 8:
            self.entered_pin += digit
            self._set_pin_display_style("active")
            self.pin_display.setText(self._format_pin_dots())

    def clear_pin(self):
        self.entered_pin = ""
        self._set_pin_display_style("normal")
        self.pin_display.setText("○ ○ ○ ○")

    def verify_pin(self):
        now_sec = int(time.time())
        step = now_sec // 30
        secret_salt = 7919
        totp_code = str((step * secret_salt + 104729) % 10000).zfill(4)

        if self.entered_pin == self.ogretmen_pin or self.entered_pin == totp_code or self.entered_pin == self.yonetici_sifre:
            self.clear_pin()
            self.unlock_board(by="Manuel PIN")
        else:
            self._set_pin_display_style("error")
            self.pin_display.setText("HATALI PIN")
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
        self.hide()

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
        """Masaüstü açıkken sağ alt köşede duran 'Tahtayı Kilitle' butonu"""
        if hasattr(self, "relock_btn") and self.relock_btn:
            self.relock_btn.show()
            return

        self.relock_btn = QPushButton("🔒 Tahtayı Kilitle")
        self.relock_btn.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.relock_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff5e4d, stop:1 #dc2626);
                color: white;
                font-weight: bold;
                padding: 10px 18px;
                border-radius: 10px;
                border: 1.5px solid #fca5a5;
                font-size: 13px;
            }
            QPushButton:hover { background: #dc2626; }
        """)
        self.relock_btn.clicked.connect(self.lock_board)

        screen_geo = QApplication.primaryScreen().geometry()
        self.relock_btn.move(screen_geo.width() - 180, screen_geo.height() - 75)
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
            if isinstance(self.lbl_status, FlatBarSegment):
                self.lbl_status.set_segment_colors(
                    accent_color=QColor(52, 211, 153, 220),
                    bg_tint=QColor(16, 185, 129, 22),
                    text_color=QColor(110, 231, 183)
                )
        else:
            self.lbl_status.setText("● Çevrimdışı (PIN)")
            if isinstance(self.lbl_status, FlatBarSegment):
                self.lbl_status.set_segment_colors(
                    accent_color=QColor(248, 113, 113, 220),
                    bg_tint=QColor(239, 68, 68, 22),
                    text_color=QColor(252, 165, 165)
                )

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
        play_alert_sound()
        self.banner.show_message(message, duration_sec)

        if self.is_locked:
            if hasattr(self, "announcement_overlay") and self.announcement_overlay:
                self.announcement_overlay.show_announcement(message, duration_sec)
        else:
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
        dlg.setStyleSheet("background: #0b1930; border: 2px solid #ef4444; border-radius: 20px; padding: 25px;")
        l = QVBoxLayout(dlg)
        icon = QLabel("🔌")
        icon.setFont(QFont("Segoe UI Emoji", 40))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(icon)
        t = QLabel("Etkileşimli Tahta Kapatılıyor...")
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
        if self.entered_pin == self.yonetici_sifre or self.entered_pin == self.ogretmen_pin:
            self.clear_pin()
            if hasattr(self, "settings_overlay") and self.settings_overlay:
                self.settings_overlay.show_settings()
        else:
            self._set_pin_display_style("error")
            self.pin_display.setText("ŞİFRE GİRİN")
            QTimer.singleShot(1500, self.clear_pin)

    def apply_new_settings(self, new_board: str, new_url: str, new_school: str = None):
        old_url = self.sunucu_url

        self.sinif_adi = new_board
        self.sunucu_url = new_url
        if new_school is not None and new_school.strip():
            self.okul_adi = new_school.strip()

        self.cfg.set("GENEL", "sinif_adi", self.sinif_adi)
        self.cfg.set("GENEL", "okul_adi", self.okul_adi)
        self.cfg.set("GENEL", "sunucu_ws_url", self.sunucu_url)
        save_config(self.cfg)

        self.lbl_class.setText(f"🖥️ {self.sinif_adi}")
        self.lbl_school.setText(f"🏫 {self.okul_adi}")
        self._fit_school_label_font()
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

        if hasattr(self, "settings_overlay") and self.settings_overlay and self.settings_overlay.isVisible():
            self.settings_overlay.handle_key_event(event)
            return

        if hasattr(self, "admin_exit_overlay") and self.admin_exit_overlay and self.admin_exit_overlay.isVisible():
            self.admin_exit_overlay.handle_key_event(event)
            return

        if (event.modifiers() == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier) 
            and event.key() == Qt.Key.Key_Q):
            if hasattr(self, "admin_exit_overlay") and self.admin_exit_overlay:
                self.admin_exit_overlay.show_prompt()
            return

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

        if key in [Qt.Key.Key_Return, Qt.Key.Key_Enter]:
            self.verify_pin()
            return

        if key == Qt.Key.Key_Backspace:
            if len(self.entered_pin) > 0:
                self.entered_pin = self.entered_pin[:-1]
                self._set_pin_display_style("active" if self.entered_pin else "normal")
                self.pin_display.setText(self._format_pin_dots())
            return
        if key == Qt.Key.Key_Delete:
            self.clear_pin()
            return

        event.ignore()

    def closeEvent(self, event):
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
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(DEVELOPER_NAME)

    # 🔒 Çift Açılış Koruması (Single Instance Mutex / Lock)
    # Sistemin yeniden başlaması, oturum kurtarma veya çift tıklama durumunda
    # 2. kopyanın açılmasını, ekranların üst üste binmesini ve karekod çakışmasını KESİN olarak engeller.
    temp_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation)
    user_identifier = os.environ.get("USER", os.environ.get("USERNAME", "etapadmin"))
    lock_file_path = os.path.join(temp_dir, f"tahta_kilit_{user_identifier}.lock")
    lock_file = QLockFile(lock_file_path)
    lock_file.setStaleLockTime(10000)  # 10 saniye sonra ölü kilitleri otomatik temizle

    if not lock_file.tryLock(150):
        lock_info = lock_file.getLockInfo()
        other_pid = lock_info[1] if lock_info and len(lock_info) > 1 else "Bilinmiyor"
        print(f"⚠️ [{APP_NAME}] Zaten çalışan bir oturum mevcut (PID: {other_pid})!")
        print("💡 Ekranların çakışmaması ve karekodun yanıp sönmemesi için 2. kopya güvenle durduruldu.")
        sys.exit(0)

    # Lock nesnesini çöp toplayıcıdan (GC) korumak için app nesnesine iliştir
    app._single_instance_lock = lock_file

    window = LockScreenWindow()
    window.show_kiosk_fullscreen()
    exit_code = app.exec()

    try:
        lock_file.unlock()
    except Exception:
        pass
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
