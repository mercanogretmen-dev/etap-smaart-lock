import asyncio
import json
import logging
import os
import re
import sys
import time
import uuid
from urllib.parse import urlparse
from typing import Dict, List, Optional
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

DATA_DIR = os.path.join(CURRENT_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB
UPLOAD_TTL_SECONDS = 900  # 15 dakika
MAX_STORED_UPLOADS = 10
DEFAULT_SCHOOL_NAME = "T.C. MİLLÎ EĞİTİM BAKANLIĞI — ETKİLEŞİMLİ TAHTA SİSTEMİ"
ALLOWED_FILE_EXTENSIONS = {
    ".pdf", ".ppt", ".pptx", ".doc", ".docx", ".xls", ".xlsx",
    ".mp3", ".wav", ".ogg", ".m4a", ".mp4", ".webm", ".mkv", ".mov",
    ".jpg", ".jpeg", ".png", ".txt", ".zip",
}


def sanitize_filename(name: str) -> str:
    """Kullanıcı dosya adından yol traversal ve geçersiz karakterleri temizler (maks. 120 karakter)."""
    base = os.path.basename((name or "").replace("\\", "/")).strip()
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", base)
    stem, ext = os.path.splitext(cleaned)
    stem = stem.strip(" .") or "dosya"
    ext = re.sub(r'[^A-Za-z0-9.]', "", ext.lower())
    max_stem_len = max(1, 120 - len(ext))
    return f"{stem[:max_stem_len]}{ext}"

try:
    from . import config
except ImportError:
    import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ETAP-Server")

app = FastAPI(title="ETAP Akıllı Kilit & Mobil Yönetim Sistemi", version="1.0.0")

# CORS izinleri (Tüm mobil cihazlar ve yerel ağ için)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    """Mobil PWA/tarayıcılarda eski JS/CSS ile yeni HTML'in karışmasını önler."""
    response = await call_next(request)
    path = request.url.path or "/"
    if path == "/" or path.endswith((".html", ".js", ".css")):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response

# -------------------------------------------------------------
# 📡 Canlı Tahta WebSocket Yöneticisi (Connection Manager)
# -------------------------------------------------------------
class BoardConnectionManager:
    def __init__(self):
        # board_id (benzersiz cihaz kimliği) -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}
        # board_id -> son görülme zamanı (timestamp)
        self.board_last_seen: Dict[str, float] = {}
        # board_id -> kilit durumu ("locked" veya "unlocked")
        self.board_status: Dict[str, str] = {}
        # board_id -> sınıf/tahta görünen adı (Örn: "9-A")
        self.board_names: Dict[str, str] = {}
        # board_id -> istemci sürümü (Örn: "v0.4.0")
        self.board_versions: Dict[str, str] = {}
        # board_id -> canlı güncelleme/durum detay mesajı
        self.board_update_msg: Dict[str, str] = {}
        # Merkezi Okul / Kurum Adı ve PIN Ayarları (Tüm bağlı tahtalara yayınlanır)
        self.school_name: str = DEFAULT_SCHOOL_NAME
        self.school_name_custom: bool = False
        self.teacher_pin_custom: bool = False
        self.admin_pin_custom: bool = False
        self.load_settings()
        # Bekleyen ekran görüntüsü yanıtları (request_id -> asyncio.Future)
        self.pending_screenshots: Dict[str, asyncio.Future] = {}
        # Sunucuda tutulan aktif duyuru (yeni bağlanan tahtalara da iletilir)
        self.active_announcement: Optional[dict] = None
        # Geçici olarak masaüstüne gönderilen dosyalar (file_id -> metadata)
        self.uploaded_files: Dict[str, dict] = {}

    def cleanup_expired_uploads(self):
        """Süresi (15 dk) dolmuş veya saklama limitini aşan en eski yükleme dosyalarını temizler."""
        now = time.time()
        expired_ids = [
            f_id for f_id, info in list(self.uploaded_files.items())
            if (now - info.get("created_at", 0) > UPLOAD_TTL_SECONDS)
            or not os.path.isfile(info.get("path", ""))
        ]
        for f_id in expired_ids:
            info = self.uploaded_files.pop(f_id, None)
            if info and info.get("path") and os.path.isfile(info["path"]):
                try:
                    os.remove(info["path"])
                except Exception:
                    pass

        while len(self.uploaded_files) > MAX_STORED_UPLOADS:
            oldest_id = min(
                self.uploaded_files.keys(),
                key=lambda k: self.uploaded_files[k].get("created_at", 0)
            )
            info = self.uploaded_files.pop(oldest_id, None)
            if info and info.get("path") and os.path.isfile(info["path"]):
                try:
                    os.remove(info["path"])
                except Exception:
                    pass

    def load_settings(self):
        """Kalıcı ayarları (okul adı, öğretmen/idare PIN) settings.json ve ortam değişkenlerinden yükler."""
        data = {}
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
            except Exception as e:
                logger.error(f"Ayarlar okunamadı: {e}")

        env_school = getattr(config, "SCHOOL_NAME", "").strip()
        if env_school:
            self.school_name = env_school
            self.school_name_custom = True
        else:
            saved_name = str(data.get("school_name", "")).strip()
            if saved_name:
                self.school_name = saved_name
                self.school_name_custom = bool(data.get("school_name_custom")) or (saved_name != DEFAULT_SCHOOL_NAME)
            else:
                self.school_name = DEFAULT_SCHOOL_NAME
                self.school_name_custom = False

        saved_teacher_pin = str(data.get("teacher_pin", "")).strip()
        if saved_teacher_pin:
            config.TEACHER_PIN = saved_teacher_pin
            self.teacher_pin_custom = bool(data.get("teacher_pin_custom", True))
        else:
            self.teacher_pin_custom = False

        saved_admin_pin = str(data.get("admin_pin", "")).strip()
        if saved_admin_pin:
            config.ADMIN_PIN = saved_admin_pin
            self.admin_pin_custom = bool(data.get("admin_pin_custom", True))
        else:
            self.admin_pin_custom = False

    def save_settings(self):
        """Okul adı ve özelleştirilmiş PIN ayarlarını settings.json içine kalıcı kaydeder."""
        payload = {
            "school_name": self.school_name,
            "school_name_custom": self.school_name_custom,
        }
        if self.teacher_pin_custom:
            payload["teacher_pin"] = config.TEACHER_PIN
            payload["teacher_pin_custom"] = True
        if self.admin_pin_custom:
            payload["admin_pin"] = config.ADMIN_PIN
            payload["admin_pin_custom"] = True

        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ayarlar kaydedilemedi: {e}")

    def save_school_name(self, name: str, custom: bool = True):
        self.school_name = name.strip()
        self.school_name_custom = bool(custom)
        self.save_settings()

    async def connect(self, board_id: str, websocket: WebSocket, name: Optional[str] = None, version: Optional[str] = None):
        await websocket.accept()
        self.active_connections[board_id] = websocket
        self.board_last_seen[board_id] = time.time()
        self.board_status[board_id] = "locked"
        self.board_names[board_id] = name or self.board_names.get(board_id, board_id)
        self.board_versions[board_id] = version or self.board_versions.get(board_id, "")
        self.board_update_msg.pop(board_id, None)
        logger.info(f"🟢 Tahta bağlandı: [{board_id}] ('{self.board_names[board_id]}') (Toplam bağlı: {len(self.active_connections)})")

    def update_name(self, board_id: str, new_name: str):
        old_name = self.board_names.get(board_id, board_id)
        self.board_names[board_id] = new_name
        logger.info(f"✏️ Tahta adı güncellendi: [{board_id}] '{old_name}' -> '{new_name}'")

    def disconnect(self, board_id: str, websocket: Optional[WebSocket] = None):
        if board_id in self.active_connections:
            # SADECE ayrılan websocket o anki aktif websocket ise sil (yeniden bağlanma çakışmalarını önler)
            if websocket is None or self.active_connections.get(board_id) == websocket:
                del self.active_connections[board_id]
                if board_id in self.board_status:
                    del self.board_status[board_id]
                if board_id in self.board_last_seen:
                    del self.board_last_seen[board_id]
                self.board_versions.pop(board_id, None)
                self.board_update_msg.pop(board_id, None)
                logger.info(f"🔴 Tahta ayrıldı ve listeden temizlendi: [{board_id}]")
            else:
                logger.info(f"ℹ️ [{board_id}] için eski bir soket kapandı, mevcut aktif soket korunuyor.")

    def is_connected(self, board_id: str) -> bool:
        return board_id in self.active_connections

    def find_board(self, identifier: str) -> Optional[str]:
        """Hem cihaz ID'sine (etap-xxx) hem de sınıf adına ('9-A') göre aktif tahtayı bulur"""
        if identifier in self.active_connections:
            return identifier
        for b_id, name in self.board_names.items():
            if name.strip().lower() == identifier.strip().lower() and b_id in self.active_connections:
                return b_id
        return None

    async def send_to_board(self, board_id: str, message: dict) -> bool:
        if board_id in self.active_connections:
            try:
                ws = self.active_connections[board_id]
                await ws.send_text(json.dumps(message))
                return True
            except Exception as e:
                logger.error(f"Mesaj gönderme hatası [{board_id}]: {e}")
                self.disconnect(board_id)
                return False
        return False

    async def broadcast_all(self, message: dict) -> int:
        success_count = 0
        disconnected = []
        for board_id, ws in list(self.active_connections.items()):
            try:
                await ws.send_text(json.dumps(message))
                success_count += 1
            except Exception:
                disconnected.append(board_id)
        for b_id in disconnected:
            self.disconnect(b_id)
        return success_count

    def get_online_boards(self, online_only: bool = True) -> List[dict]:
        boards = []
        if online_only:
            target_ids = list(self.active_connections.keys())
        else:
            target_ids = list(set(list(self.active_connections.keys()) + list(self.board_last_seen.keys())))

        for b_id in target_ids:
            boards.append({
                "id": b_id,
                "name": self.board_names.get(b_id, b_id),
                "status": self.board_status.get(b_id, "locked"),
                "online": b_id in self.active_connections,
                "last_seen": int(self.board_last_seen.get(b_id, time.time())),
                "version": self.board_versions.get(b_id, ""),
                "update_msg": self.board_update_msg.get(b_id, "")
            })
        return boards

    def cleanup_offline(self) -> int:
        removed = 0
        all_ids = set(list(self.board_last_seen.keys()) + list(self.board_names.keys()))
        for b_id in all_ids:
            if b_id not in self.active_connections:
                if b_id in self.board_last_seen:
                    del self.board_last_seen[b_id]
                if b_id in self.board_names:
                    del self.board_names[b_id]
                if b_id in self.board_status:
                    del self.board_status[b_id]
                self.board_versions.pop(b_id, None)
                self.board_update_msg.pop(b_id, None)
                removed += 1
        return removed


manager = BoardConnectionManager()

# -------------------------------------------------------------
# 📩 API İstek Modelleri
# -------------------------------------------------------------
class UnlockRequest(BaseModel):
    board_id: str
    pin: str
    qr_token: Optional[str] = None

class LockRequest(BaseModel):
    board_id: str
    pin: str

class PoweroffRequest(BaseModel):
    board_id: str
    pin: str

class BroadcastRequest(BaseModel):
    admin_pin: str
    target: str  # "all" veya belirli bir "board_id" (örn: "9-A")
    message: str
    duration_sec: int = 120  # Ekranda kaç saniye aksın
    link_url: Optional[str] = None
    link_label: Optional[str] = None

class BroadcastClearRequest(BaseModel):
    admin_pin: str
    target: str = "all"

class SchoolSettingsRequest(BaseModel):
    admin_pin: str
    school_name: str

class ScreenshotRequest(BaseModel):
    board_id: str
    admin_pin: str
    width: int = 960
    quality: int = 72
    last_hash: Optional[str] = None

class ThumbnailsRequest(BaseModel):
    admin_pin: str
    width: int = 320
    quality: int = 40
    hashes: Dict[str, str] = {}

class BulkActionRequest(BaseModel):
    admin_pin: str

class BoardUpdateRequest(BaseModel):
    board_id: str
    admin_pin: str

class AdminVerifyRequest(BaseModel):
    admin_pin: str

class PinUpdateRequest(BaseModel):
    current_admin_pin: str
    new_teacher_pin: Optional[str] = None
    new_admin_pin: Optional[str] = None

# -------------------------------------------------------------
# 🌐 WebSocket Uç Noktası (Pardus ETAP Tahtaları Buraya Bağlanır)
# -------------------------------------------------------------
@app.websocket("/ws/board/{board_id}")
async def websocket_board_endpoint(websocket: WebSocket, board_id: str, name: Optional[str] = None):
    query_name = websocket.query_params.get("name")
    query_version = websocket.query_params.get("version")
    query_school = (websocket.query_params.get("school_name") or "").strip()
    initial_name = query_name or name or board_id
    await manager.connect(board_id, websocket, initial_name, version=query_version)
    try:
        # Sunucu Render vb. yeniden başlatmadan varsayılan kurum adıyla açıldıysa,
        # bağlanan tahtadaki kayıtlı gerçek kurum adını sunucuya otomatik geri yükle
        if (
            not manager.school_name_custom
            and query_school
            and query_school != DEFAULT_SCHOOL_NAME
        ):
            manager.save_school_name(query_school, custom=True)
            logger.info(f"🏫 Kurum adı tahta bildiriminden geri yüklendi: '{query_school}'")

        # Tahtaya ilk bağlantı onayı ve merkezi okul/PIN durumunu gönder
        await websocket.send_text(json.dumps({
            "action": "welcome",
            "board_id": board_id,
            "name": manager.board_names.get(board_id, initial_name),
            "school_name": manager.school_name,
            "school_name_custom": manager.school_name_custom,
            "teacher_pin": config.TEACHER_PIN,
            "teacher_pin_custom": manager.teacher_pin_custom,
            "message": f"Bağlantı kuruldu: {manager.board_names.get(board_id, initial_name)}"
        }))

        # Varsa süresi dolmamış aktif duyuruyu yeni bağlanan tahtaya da ilet
        if manager.active_announcement:
            ann_age = time.time() - manager.active_announcement.get("timestamp", 0)
            ann_dur = manager.active_announcement.get("duration_sec", 120)
            if ann_age < ann_dur:
                replay_payload = dict(manager.active_announcement)
                replay_payload["duration_sec"] = max(10, int(ann_dur - ann_age))
                await websocket.send_text(json.dumps(replay_payload))

        while True:
            # Tahtadan gelen kalp atışı (heartbeat) ve durum bildirimleri
            data_text = await websocket.receive_text()
            try:
                msg = json.loads(data_text)
                action = msg.get("action")
                manager.board_last_seen[board_id] = time.time()

                if action == "status_update":
                    manager.board_status[board_id] = msg.get("status", "locked")
                    if "detail" in msg:
                        manager.board_update_msg[board_id] = str(msg.get("detail", ""))
                    if msg.get("version"):
                        manager.board_versions[board_id] = str(msg["version"])
                elif action == "update_name":
                    new_name = msg.get("name", "").strip()
                    if new_name:
                        manager.update_name(board_id, new_name)
                        await websocket.send_text(json.dumps({
                            "action": "name_updated",
                            "name": new_name
                        }))
                elif action == "screenshot_response":
                    req_id = msg.get("request_id")
                    if req_id and req_id in manager.pending_screenshots:
                        future = manager.pending_screenshots.pop(req_id, None)
                        if future and not future.done():
                            future.set_result(msg)
                elif action == "ping":
                    await websocket.send_text(json.dumps({"action": "pong", "time": time.time()}))
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        manager.disconnect(board_id, websocket)
    except Exception as e:
        logger.error(f"WebSocket istisnası [{board_id}]: {e}")
        manager.disconnect(board_id, websocket)

# -------------------------------------------------------------
# 📱 Mobil REST API Uç Noktaları (Öğretmen ve Müdür Telefonu)
# -------------------------------------------------------------
@app.get("/api/boards")
async def list_boards(online_only: bool = True):
    """Sadece çevrimiçi olan veya tüm akıllı tahtaları listeler"""
    return {
        "success": True,
        "boards": manager.get_online_boards(online_only=online_only)
    }

@app.post("/api/boards/cleanup")
def cleanup_boards():
    """Çevrimdışı kalan eski/hayalet tahta kayıtlarını temizler"""
    count = manager.cleanup_offline()
    return {
        "success": True,
        "message": f"{count} adet çevrimdışı tahta kaydı temizlendi."
    }

@app.post("/api/unlock")
async def unlock_board(req: UnlockRequest):
    """Öğretmen telefonundan kilidi açma isteği"""
    # 1. Ortak Öğretmen PIN'ini doğrula
    if req.pin != config.TEACHER_PIN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hatalı Öğretmen PIN Kodu!"
        )

    # 2. Tahtayı bul (cihaz ID'si veya sınıf adıyla)
    target_id = manager.find_board(req.board_id)
    if not target_id or not manager.is_connected(target_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{req.board_id}' isimli tahta şu anda çevrimdışı! (İnterneti veya kilit programı kapalı olabilir)"
        )

    # 3. Tahtaya WebSocket üzerinden kilit açma emri gönder
    board_name = manager.board_names.get(target_id, target_id)
    sent = await manager.send_to_board(target_id, {
        "action": "unlock",
        "by": "teacher",
        "timestamp": time.time()
    })

    if sent:
        manager.board_status[target_id] = "unlocked"
        return {
            "success": True,
            "message": f"{board_name} tahtasının kilidi başarıyla açıldı! 🔓"
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Tahtaya kilit açma sinyali iletilemedi."
        )

@app.post("/api/lock")
async def lock_board(req: LockRequest):
    """Öğretmen telefonundan dersi bitirip tahtayı kilitleme isteği"""
    if req.pin != config.TEACHER_PIN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hatalı Öğretmen PIN Kodu!"
        )

    target_id = manager.find_board(req.board_id)
    if not target_id or not manager.is_connected(target_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{req.board_id}' tahtası çevrimdışı."
        )

    board_name = manager.board_names.get(target_id, target_id)
    sent = await manager.send_to_board(target_id, {
        "action": "lock",
        "by": "teacher",
        "timestamp": time.time()
    })

    if sent:
        manager.board_status[target_id] = "locked"
        return {
            "success": True,
            "message": f"{board_name} tahtası kilitlendi! 🔒"
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Kilit komutu iletilemedi."
        )

@app.post("/api/poweroff")
async def poweroff_board(req: PoweroffRequest):
    """Öğretmen veya İdare tarafından tahtayı tamamen kapatma (shutdown) emri"""
    if req.pin != config.TEACHER_PIN and req.pin != config.ADMIN_PIN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hatalı PIN Kodu! Tahtayı kapatmak için yetkili şifresi gereklidir."
        )

    target_id = manager.find_board(req.board_id)
    if not target_id or not manager.is_connected(target_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{req.board_id}' tahtası çevrimdışı."
        )

    board_name = manager.board_names.get(target_id, target_id)
    sent = await manager.send_to_board(target_id, {
        "action": "poweroff",
        "by": "remote_user",
        "timestamp": time.time()
    })

    if sent:
        return {
            "success": True,
            "message": f"'{board_name}' tahtasına kapatma emri iletildi. Tahta kapanıyor... 🔌"
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Kapatma sinyali iletilemedi."
        )

@app.post("/api/broadcast")
async def broadcast_announcement(req: BroadcastRequest):
    """Müdür / İdare tarafından mavi ışıklı kayan bant duyurusu ve web bağlantısı gönderme"""
    # 1. Müdür PIN'ini doğrula
    if req.admin_pin != config.ADMIN_PIN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hatalı Müdür/İdare Giriş Kodu!"
        )

    if not req.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duyuru metni boş olamaz!"
        )

    normalized_url = ""
    raw_url = (req.link_url or "").strip()
    if raw_url:
        parsed = urlparse(raw_url)
        if "://" in raw_url or parsed.scheme:
            if parsed.scheme.lower() not in ("http", "https"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Geçersiz bağlantı adresi! Yalnızca http:// veya https:// desteklenir."
                )
            normalized_url = raw_url
        else:
            normalized_url = f"https://{raw_url}"

    payload = {
        "action": "banner_message",
        "message": req.message.strip(),
        "link_url": normalized_url,
        "link_label": (req.link_label or "").strip(),
        "duration_sec": req.duration_sec,
        "timestamp": time.time()
    }

    if req.target == "all":
        manager.active_announcement = payload
        count = await manager.broadcast_all(payload)
        return {
            "success": True,
            "message": f"Duyuru açık olan {count} tahtaya başarıyla iletildi! 📢"
        }
    else:
        target_id = manager.find_board(req.target)
        if not target_id or not manager.is_connected(target_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"'{req.target}' tahtası şu anda çevrimdışı."
            )
        sent = await manager.send_to_board(target_id, payload)
        if sent:
            board_name = manager.board_names.get(target_id, target_id)
            return {
                "success": True,
                "message": f"Duyuru '{board_name}' tahtasına başarıyla iletildi!"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Duyuru tahtaya iletilemedi."
            )

@app.post("/api/broadcast/clear")
async def clear_broadcast_announcement(req: BroadcastClearRequest):
    """Müdür / İdare tarafından tahtalardaki aktif duyuruları temizleme"""
    if req.admin_pin != config.ADMIN_PIN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hatalı Müdür/İdare Giriş Kodu!"
        )

    payload = {
        "action": "clear_announcement",
        "timestamp": time.time()
    }
    manager.active_announcement = None

    if req.target == "all":
        count = await manager.broadcast_all(payload)
        return {
            "success": True,
            "message": f"Aktif duyurular açık olan {count} tahtadan temizlendi! 🧹"
        }
    else:
        target_id = manager.find_board(req.target)
        if not target_id or not manager.is_connected(target_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"'{req.target}' tahtası şu anda çevrimdışı."
            )
        sent = await manager.send_to_board(target_id, payload)
        if sent:
            board_name = manager.board_names.get(target_id, target_id)
            return {
                "success": True,
                "message": f"Aktif duyuru '{board_name}' tahtasından temizlendi! 🧹"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Temizleme komutu iletilemedi."
            )

@app.get("/api/settings/school")
async def get_school_settings():
    """Tüm tahtalarda görüntülenen okul/kurum adını döndürür"""
    return {
        "success": True,
        "school_name": manager.school_name
    }

@app.post("/api/settings/school")
async def update_school_settings(req: SchoolSettingsRequest):
    """Müdür tarafından kurum adını değiştirir ve tüm bağlı tahtalara anında yayınlar"""
    if req.admin_pin != config.ADMIN_PIN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hatalı Müdür/İdare Giriş Kodu!"
        )

    name = req.school_name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Okul / Kurum adı boş olamaz!"
        )

    manager.save_school_name(name)
    count = await manager.broadcast_all({
        "action": "update_school_name",
        "school_name": name,
        "timestamp": time.time()
    })

    return {
        "success": True,
        "school_name": name,
        "message": f"Okul adı '{name}' olarak güncellendi ve {count} bağlı tahtaya anında iletildi! 🏫"
    }


@app.post("/api/admin/verify")
async def verify_admin_login(req: AdminVerifyRequest):
    """Mobil İdare Paneli giriş şifresini doğrular"""
    if (req.admin_pin or "").strip() != config.ADMIN_PIN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hatalı Müdür/İdare Giriş Kodu!"
        )
    return {
        "success": True,
        "message": "İdare girişi doğrulandı."
    }


@app.post("/api/settings/pins")
async def update_security_pins(req: PinUpdateRequest):
    """İdare panelinden Öğretmen PIN ve/veya İdare PIN kodlarını günceller"""
    if (req.current_admin_pin or "").strip() != config.ADMIN_PIN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hatalı Müdür/İdare Giriş Kodu!"
        )

    new_teacher = (req.new_teacher_pin or "").strip()
    new_admin = (req.new_admin_pin or "").strip()

    if not new_teacher and not new_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="En az bir yeni PIN kodu giriniz!"
        )

    if new_teacher and not re.fullmatch(r"\d{4,8}", new_teacher):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PIN kodu 4 ile 8 hane arasında sadece rakamlardan oluşmalıdır!"
        )
    if new_admin and not re.fullmatch(r"\d{4,8}", new_admin):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PIN kodu 4 ile 8 hane arasında sadece rakamlardan oluşmalıdır!"
        )

    teacher_updated = False
    admin_updated = False
    boards_synced = 0

    if new_teacher:
        config.TEACHER_PIN = new_teacher
        manager.teacher_pin_custom = True
        teacher_updated = True
        boards_synced = await manager.broadcast_all({
            "action": "update_teacher_pin",
            "teacher_pin": new_teacher,
            "timestamp": time.time(),
        })

    if new_admin:
        config.ADMIN_PIN = new_admin
        manager.admin_pin_custom = True
        admin_updated = True

    manager.save_settings()

    msg_parts = []
    if teacher_updated:
        msg_parts.append(f"Öğretmen PIN güncellendi ({boards_synced} tahtaya senkronize edildi)")
    if admin_updated:
        msg_parts.append("İdare PIN güncellendi")

    return {
        "success": True,
        "teacher_pin_updated": teacher_updated,
        "admin_pin_updated": admin_updated,
        "boards_synced": boards_synced,
        "message": " ve ".join(msg_parts) + "! 🔐"
    }

# -------------------------------------------------------------
# 📸 Uzaktan Canlı Ekran Görüntüsü & Önizleme Duvarı API'leri
# -------------------------------------------------------------
async def _fetch_board_frame(
    target_id: str,
    width: int,
    quality: int,
    last_hash: str = "",
    timeout: float = 7.0,
) -> dict:
    """Tek bir tahtadan WebSocket üzerinden akıllı ekran görüntüsü (Smart Diff destekli) ister."""
    request_id = str(uuid.uuid4())[:8]
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    manager.pending_screenshots[request_id] = future

    try:
        sent = await manager.send_to_board(target_id, {
            "action": "take_screenshot",
            "request_id": request_id,
            "width": width,
            "quality": quality,
            "last_hash": last_hash,
            "timestamp": time.time(),
        })
        if not sent:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Tahtaya ekran görüntüsü alma emri iletilemedi."
            )

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Tahtadan ekran görüntüsü zamanında alınamadı (zaman aşımı)."
            )
    finally:
        manager.pending_screenshots.pop(request_id, None)


@app.post("/api/board/screenshot")
async def get_board_screenshot(req: ScreenshotRequest):
    """Müdür / İdare panelinden tahtanın canlı ekran görüntüsünü (Smart Diff destekli) çeker"""
    if req.admin_pin != config.ADMIN_PIN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hatalı Müdür/İdare Giriş Kodu!"
        )

    target_id = manager.find_board(req.board_id)
    if not target_id or not manager.is_connected(target_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{req.board_id}' tahtası şu anda çevrimdışı! (Kilit uygulaması veya internet kapalı olabilir)"
        )

    width = max(240, min(1280, req.width))
    quality = max(25, min(85, req.quality))
    result = await _fetch_board_frame(
        target_id,
        width=width,
        quality=quality,
        last_hash=(req.last_hash or "").strip(),
        timeout=7.0,
    )
    return {
        "success": True,
        "board_id": req.board_id,
        "name": manager.board_names.get(target_id, req.board_id),
        "image": result.get("image", ""),
        "unchanged": bool(result.get("unchanged", False)),
        "frame_hash": str(result.get("frame_hash", "")),
        "timestamp": result.get("timestamp", time.time()),
    }


@app.post("/api/boards/thumbnails")
async def get_boards_thumbnails(req: ThumbnailsRequest):
    """Müdür Önizleme Duvarı için bağlı tüm tahtalardan hafif küçük kareleri toplu ve Smart Diff ile ister"""
    if req.admin_pin != config.ADMIN_PIN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hatalı Müdür/İdare Giriş Kodu!"
        )

    width = max(160, min(480, req.width))
    quality = max(20, min(65, req.quality))
    connected_ids = list(manager.active_connections.keys())

    async def _grab_one(b_id: str):
        try:
            res = await _fetch_board_frame(
                b_id,
                width=width,
                quality=quality,
                last_hash=str(req.hashes.get(b_id, "") or "").strip(),
                timeout=4.0,
            )
            return b_id, {
                "unchanged": bool(res.get("unchanged", False)),
                "image": res.get("image", ""),
                "frame_hash": str(res.get("frame_hash", "")),
                "timestamp": res.get("timestamp", time.time()),
            }
        except Exception:
            return b_id, None

    results = await asyncio.gather(*[_grab_one(b_id) for b_id in connected_ids])
    thumbnails = {b_id: data for b_id, data in results if data is not None}
    return {
        "success": True,
        "thumbnails": thumbnails,
        "count": len(thumbnails),
    }

# -------------------------------------------------------------
# ⚡ Toplu Yönetim API'leri (Tüm Tahtaları Kilitle / Aç / Kapat)
# -------------------------------------------------------------
@app.post("/api/bulk/lock")
async def bulk_lock_boards(req: BulkActionRequest):
    """Müdür panelinden açık olan tüm tahtaları tek tıkla kilitler"""
    if req.admin_pin != config.ADMIN_PIN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hatalı Müdür/İdare Giriş Kodu!"
        )

    count = await manager.broadcast_all({
        "action": "lock",
        "by": "admin",
        "timestamp": time.time()
    })
    for b_id in manager.active_connections:
        manager.board_status[b_id] = "locked"

    return {
        "success": True,
        "count": count,
        "message": f"Bağlı olan {count} adet akıllı tahta başarıyla kilitlendi! 🔒"
    }

@app.post("/api/bulk/unlock")
async def bulk_unlock_boards(req: BulkActionRequest):
    """Müdür panelinden tüm tahtaların kilidini topluca açar"""
    if req.admin_pin != config.ADMIN_PIN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hatalı Müdür/İdare Giriş Kodu!"
        )

    count = await manager.broadcast_all({
        "action": "unlock",
        "by": "admin",
        "timestamp": time.time()
    })
    for b_id in manager.active_connections:
        manager.board_status[b_id] = "unlocked"

    return {
        "success": True,
        "count": count,
        "message": f"Bağlı olan {count} adet akıllı tahtanın kilidi başarıyla açıldı! 🔓"
    }

@app.post("/api/bulk/poweroff")
async def bulk_poweroff_boards(req: BulkActionRequest):
    """Müdür panelinden açık olan tüm tahtaları tamamen kapatır (shutdown)"""
    if req.admin_pin != config.ADMIN_PIN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hatalı Müdür/İdare Giriş Kodu!"
        )

    count = await manager.broadcast_all({
        "action": "poweroff",
        "by": "admin",
        "timestamp": time.time()
    })

    return {
        "success": True,
        "count": count,
        "message": f"Bağlı olan {count} adet tahtaya kapatma (güç kesme) emri gönderildi! 🔌"
    }

@app.post("/api/bulk/update")
async def bulk_update_boards(req: BulkActionRequest):
    """Müdür panelinden açık olan tüm tahtalara tek tıkla uzaktan güncelleme komutu gönderir"""
    if req.admin_pin != config.ADMIN_PIN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hatalı Müdür/İdare Giriş Kodu!"
        )

    count = await manager.broadcast_all({
        "action": "update_client",
        "by": "admin",
        "timestamp": time.time()
    })
    for b_id in manager.active_connections:
        manager.board_status[b_id] = "updating"
        manager.board_update_msg[b_id] = "Güncelleme başlatıldı..."

    return {
        "success": True,
        "count": count,
        "message": f"Bağlı olan {count} adet tahtaya uzaktan güncelleme emri gönderildi! 🔄"
    }

@app.post("/api/board/update")
async def update_single_board(req: BoardUpdateRequest):
    """Müdür panelinden seçili tek bir tahtaya uzaktan güncelleme komutu gönderir"""
    if req.admin_pin != config.ADMIN_PIN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hatalı Müdür/İdare Giriş Kodu!"
        )

    target_id = manager.find_board(req.board_id)
    if not target_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{req.board_id}' tahtası şu anda çevrimdışı."
        )

    sent = await manager.send_to_board(target_id, {
        "action": "update_client",
        "by": "admin",
        "timestamp": time.time()
    })
    if not sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Tahtaya güncelleme komutu iletilemedi."
        )

    manager.board_status[target_id] = "updating"
    manager.board_update_msg[target_id] = "Güncelleme başlatıldı..."

    return {
        "success": True,
        "board_id": target_id,
        "message": f"'{manager.board_names.get(target_id, target_id)}' tahtasına uzaktan güncelleme komutu gönderildi! 🔄"
    }

# -------------------------------------------------------------
# 📁 Yönetici Panelinden Tahta Masaüstüne Dosya Gönderme API'leri
# -------------------------------------------------------------
@app.post("/api/files/send")
async def send_file_to_boards(
    admin_pin: str = Form(...),
    target: str = Form("all"),
    open_after: bool = Form(False),
    file: UploadFile = File(...),
):
    """Telefondan yüklenen PDF/Office/medya dosyasını hedef tahtaların masaüstüne aktarır."""
    if admin_pin != config.ADMIN_PIN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hatalı Müdür/İdare Giriş Kodu!"
        )

    target_id = None
    if target == "all":
        if len(manager.active_connections) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Şu anda bağlı çevrimiçi akıllı tahta bulunmuyor."
            )
    else:
        target_id = manager.find_board(target)
        if not target_id or not manager.is_connected(target_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"'{target}' tahtası şu anda çevrimdışı."
            )

    safe_name = sanitize_filename(file.filename or "")
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in ALLOWED_FILE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Desteklenmeyen dosya türü! İzin verilenler: PDF, PPTX, DOCX, XLSX, MP3, MP4 vb."
        )

    manager.cleanup_expired_uploads()

    file_id = str(uuid.uuid4())[:12]
    disk_path = os.path.join(UPLOAD_DIR, f"{file_id}_{safe_name}")
    total_bytes = 0

    try:
        with open(disk_path, "wb") as out_f:
            while True:
                chunk = await file.read(65536)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_BYTES:
                    out_f.close()
                    if os.path.isfile(disk_path):
                        os.remove(disk_path)
                    raise HTTPException(
                        status_code=413,
                        detail="Dosya boyutu en fazla 25 MB olabilir!"
                    )
                out_f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        if os.path.isfile(disk_path):
            try:
                os.remove(disk_path)
            except Exception:
                pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Dosya sunucuya kaydedilemedi: {e}"
        )
    finally:
        await file.close()

    if total_bytes == 0:
        if os.path.isfile(disk_path):
            os.remove(disk_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Boş dosya gönderilemez!"
        )

    manager.uploaded_files[file_id] = {
        "file_id": file_id,
        "filename": safe_name,
        "path": disk_path,
        "size_bytes": total_bytes,
        "created_at": time.time(),
    }
    manager.cleanup_expired_uploads()

    ws_payload = {
        "action": "receive_file",
        "file_id": file_id,
        "filename": safe_name,
        "size_bytes": total_bytes,
        "download_path": f"/api/files/download/{file_id}",
        "open_after": bool(open_after),
        "timestamp": time.time(),
    }

    if target == "all":
        count = await manager.broadcast_all(ws_payload)
        if count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Şu anda bağlı çevrimiçi akıllı tahta bulunmuyor."
            )
        msg = f"'{safe_name}' dosyası {count} tahtanın masaüstüne gönderildi! 📁"
    else:
        sent = await manager.send_to_board(target_id, ws_payload)
        if not sent:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Dosya bildirimi tahtaya iletilemedi."
            )
        count = 1
        board_name = manager.board_names.get(target_id, target_id)
        msg = f"'{safe_name}' dosyası '{board_name}' tahtasının masaüstüne gönderildi! 📁"

    return {
        "success": True,
        "file_id": file_id,
        "filename": safe_name,
        "size_bytes": total_bytes,
        "count": count,
        "message": msg,
    }


@app.get("/api/files/download/{file_id}")
async def download_uploaded_file(file_id: str):
    """Tahtaların masaüstüne kaydetmek üzere geçici dosyayı indirir."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", file_id or ""):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dosya bulunamadı.")

    manager.cleanup_expired_uploads()
    info = manager.uploaded_files.get(file_id)
    if not info or not os.path.isfile(info.get("path", "")):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dosya bulunamadı veya indirme süresi doldu."
        )

    return FileResponse(
        info["path"],
        filename=info["filename"],
        media_type="application/octet-stream",
    )

# -------------------------------------------------------------
# 📂 Statik Dosyalar & PWA (Manifest & Service Worker)
# -------------------------------------------------------------
STATIC_DIR = os.path.join(CURRENT_DIR, "static")

@app.get("/manifest.json")
async def get_manifest():
    return FileResponse(os.path.join(STATIC_DIR, "manifest.json"), media_type="application/manifest+json")

@app.get("/sw.js")
async def get_service_worker():
    response = FileResponse(os.path.join(STATIC_DIR, "sw.js"), media_type="application/javascript")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response

if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
