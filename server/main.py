import json
import logging
import os
import sys
import time
from typing import Dict, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

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
        # board_id -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}
        # board_id -> son görülme zamanı (timestamp)
        self.board_last_seen: Dict[str, float] = {}
        # board_id -> kilit durumu ("locked" veya "unlocked")
        self.board_status: Dict[str, str] = {}

    async def connect(self, board_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[board_id] = websocket
        self.board_last_seen[board_id] = time.time()
        self.board_status[board_id] = "locked"
        logger.info(f"🟢 Tahta bağlandı: [{board_id}] (Toplam bağlı: {len(self.active_connections)})")

    def disconnect(self, board_id: str):
        if board_id in self.active_connections:
            del self.active_connections[board_id]
        if board_id in self.board_status:
            del self.board_status[board_id]
        logger.info(f"🔴 Tahta ayrıldı: [{board_id}]")

    def is_connected(self, board_id: str) -> bool:
        return board_id in self.active_connections

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

    def get_online_boards(self) -> List[dict]:
        boards = []
        for b_id, last_time in self.board_last_seen.items():
            boards.append({
                "id": b_id,
                "status": self.board_status.get(b_id, "locked"),
                "online": b_id in self.active_connections,
                "last_seen": int(last_time)
            })
        return boards


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

class BroadcastRequest(BaseModel):
    admin_pin: str
    target: str  # "all" veya belirli bir "board_id" (örn: "9-A")
    message: str
    duration_sec: int = 60  # Ekranda kaç saniye aksın

# -------------------------------------------------------------
# 🌐 WebSocket Uç Noktası (Pardus ETAP Tahtaları Buraya Bağlanır)
# -------------------------------------------------------------
@app.websocket("/ws/board/{board_id}")
async def websocket_board_endpoint(websocket: WebSocket, board_id: str):
    await manager.connect(board_id, websocket)
    try:
        # Tahtaya ilk bağlantı onayı gönder
        await websocket.send_text(json.dumps({
            "action": "welcome",
            "board_id": board_id,
            "message": f"Bağlantı kuruldu: {board_id}"
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
                elif action == "ping":
                    await websocket.send_text(json.dumps({"action": "pong", "time": time.time()}))
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        manager.disconnect(board_id)
    except Exception as e:
        logger.error(f"WebSocket istisnası [{board_id}]: {e}")
        manager.disconnect(board_id)

# -------------------------------------------------------------
# 📱 Mobil REST API Uç Noktaları (Öğretmen ve Müdür Telefonu)
# -------------------------------------------------------------
@app.get("/api/boards")
async def list_boards():
    """Çevrimiçi olan tüm akıllı tahtaları listeler"""
    return {
        "success": True,
        "boards": manager.get_online_boards()
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

    # 2. Tahtanın çevrimiçi olup olmadığını kontrol et
    if not manager.is_connected(req.board_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{req.board_id} isimli tahta şu anda çevrimdışı! (İnterneti veya kilit programı kapalı olabilir)"
        )

    # 3. Tahtaya WebSocket üzerinden kilit açma emri gönder
    sent = await manager.send_to_board(req.board_id, {
        "action": "unlock",
        "by": "teacher",
        "timestamp": time.time()
    })

    if sent:
        manager.board_status[req.board_id] = "unlocked"
        return {
            "success": True,
            "message": f"{req.board_id} tahtasının kilidi başarıyla açıldı! 🔓"
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

    if not manager.is_connected(req.board_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{req.board_id} tahtası çevrimdışı."
        )

    sent = await manager.send_to_board(req.board_id, {
        "action": "lock",
        "by": "teacher",
        "timestamp": time.time()
    })

    if sent:
        manager.board_status[req.board_id] = "locked"
        return {
            "success": True,
            "message": f"{req.board_id} tahtası kilitlendi! 🔒"
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Kilit komutu iletilemedi."
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
        if not manager.is_connected(req.target):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{req.target} tahtası şu anda çevrimdışı."
            )
        sent = await manager.send_to_board(req.target, payload)
        if sent:
            return {
                "success": True,
                "message": f"Duyuru {req.target} tahtasına başarıyla iletildi!"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Duyuru tahtaya iletilemedi."
            )

# -------------------------------------------------------------
# 📂 Statik Dosyalar (Telefon Arayüzü / Mobil Web App)
# -------------------------------------------------------------
STATIC_DIR = os.path.join(CURRENT_DIR, "static")
if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
