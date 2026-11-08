import asyncio
import json
import logging
import os
import sys
import time
import uuid
from typing import Dict, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, status
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

try:
    import config
except ImportError:
    from . import config

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
        # Merkezi Okul / Kurum Adı (Tüm bağlı tahtalara yayınlanır)
        self.school_name: str = self.load_school_name()
        # Bekleyen ekran görüntüsü yanıtları (request_id -> asyncio.Future)
        self.pending_screenshots: Dict[str, asyncio.Future] = {}

    def load_school_name(self) -> str:
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("school_name", "T.C. MİLLÎ EĞİTİM BAKANLIĞI — ETKİLEŞİMLİ TAHTA SİSTEMİ")
            except Exception:
                pass
        return "T.C. MİLLÎ EĞİTİM BAKANLIĞI — ETKİLEŞİMLİ TAHTA SİSTEMİ"

    def save_school_name(self, name: str):
        self.school_name = name
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump({"school_name": name}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ayarlar kaydedilemedi: {e}")

    async def connect(self, board_id: str, websocket: WebSocket, name: Optional[str] = None):
        await websocket.accept()
        self.active_connections[board_id] = websocket
        self.board_last_seen[board_id] = time.time()
        self.board_status[board_id] = "locked"
        self.board_names[board_id] = name or self.board_names.get(board_id, board_id)
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
                "last_seen": int(self.board_last_seen.get(b_id, time.time()))
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
    duration_sec: int = 60  # Ekranda kaç saniye aksın

class SchoolSettingsRequest(BaseModel):
    admin_pin: str
    school_name: str

class ScreenshotRequest(BaseModel):
    board_id: str
    admin_pin: str

class BulkActionRequest(BaseModel):
    admin_pin: str

# -------------------------------------------------------------
# 🌐 WebSocket Uç Noktası (Pardus ETAP Tahtaları Buraya Bağlanır)
# -------------------------------------------------------------
@app.websocket("/ws/board/{board_id}")
async def websocket_board_endpoint(websocket: WebSocket, board_id: str, name: Optional[str] = None):
    query_name = websocket.query_params.get("name")
    initial_name = query_name or name or board_id
    await manager.connect(board_id, websocket, initial_name)
    try:
        # Tahtaya ilk bağlantı onayı ve merkezi okul adını gönder
        await websocket.send_text(json.dumps({
            "action": "welcome",
            "board_id": board_id,
            "name": manager.board_names.get(board_id, initial_name),
            "school_name": manager.school_name,
            "message": f"Bağlantı kuruldu: {manager.board_names.get(board_id, initial_name)}"
        }))

        while True:
            # Tahtadan gelen kalp atışı (heartbeat) ve durum bildirimleri
            data_text = await websocket.receive_text()
            try:
                msg = json.loads(data_text)
                action = msg.get("action")
                manager.board_last_seen[board_id] = time.time()

                if action == "status_update":
                    manager.board_status[board_id] = msg.get("status", "locked")
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
    """Müdür / İdare tarafından mavi ışıklı kayan bant duyurusu gönderme"""
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

    payload = {
        "action": "banner_message",
        "message": req.message.strip(),
        "duration_sec": req.duration_sec,
        "timestamp": time.time()
    }

    if req.target == "all":
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

# -------------------------------------------------------------
# 📸 Uzaktan Canlı Ekran Görüntüsü Alma API'si
# -------------------------------------------------------------
@app.post("/api/board/screenshot")
async def get_board_screenshot(req: ScreenshotRequest):
    """Müdür / İdare panelinden tahtanın canlı ekran görüntüsünü anında çeker"""
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

    import uuid
    request_id = str(uuid.uuid4())[:8]
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    manager.pending_screenshots[request_id] = future

    # Tahtaya ekran görüntüsü alma emri gönder
    sent = await manager.send_to_board(target_id, {
        "action": "take_screenshot",
        "request_id": request_id,
        "timestamp": time.time()
    })

    if not sent:
        manager.pending_screenshots.pop(request_id, None)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Tahtaya ekran görüntüsü alma emri iletilemedi."
        )

    try:
        # En fazla 7 saniye içinde tahtadan sıkıştırılmış Base64 görüntüyü bekle
        result = await asyncio.wait_for(future, timeout=7.0)
        return {
            "success": True,
            "board_id": req.board_id,
            "name": manager.board_names.get(target_id, req.board_id),
            "image": result.get("image"),
            "timestamp": result.get("timestamp", time.time())
        }
    except asyncio.TimeoutError:
        manager.pending_screenshots.pop(request_id, None)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Tahtadan ekran görüntüsü zamanında alınamadı (zaman aşımı)."
        )

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
