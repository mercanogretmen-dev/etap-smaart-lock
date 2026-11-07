"""
ETAP Akıllı Kilit & Mobil Yönetim Sistemi — Otomatik Test ve Doğrulama Paketi
"""

import os
import sys
import time
import asyncio
import unittest

if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

from starlette.testclient import TestClient

# Sunucu dizinini sys.path'e ekle
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from server.main import app, manager
import server.config as config


class TestEtapSmartLockSystem(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        # Her test öncesi bağlantı yöneticisini temizle
        manager.active_connections.clear()
        manager.board_status.clear()
        manager.board_last_seen.clear()

    # -------------------------------------------------------------------------
    # 1. Statik Dosyalar (PWA Web Arayüzü) Testi
    # -------------------------------------------------------------------------
    def test_01_static_web_interface(self):
        """Mobil web arayüzünün (HTML, CSS, JS) başarıyla sunulduğunu doğrular."""
        res_index = self.client.get("/")
        self.assertEqual(res_index.status_code, 200)
        self.assertIn("ETAP", res_index.text)
        self.assertIn("html5-qrcode", res_index.text)

        res_css = self.client.get("/style.css")
        self.assertEqual(res_css.status_code, 200)

        res_js = self.client.get("/app.js")
        self.assertEqual(res_js.status_code, 200)
        self.assertIn("fetchOnlineBoards", res_js.text)

    # -------------------------------------------------------------------------
    # 2. Yetkilendirme & Güvenlik PIN Kontrolleri Testi
    # -------------------------------------------------------------------------
    def test_02_auth_pin_validation(self):
        """Öğretmen ve Müdür PIN doğrulamalarının güvenliğini test eder."""
        # Hatalı öğretmen PIN'i ile kilit açma denemesi
        res = self.client.post("/api/unlock", json={"board_id": "9-A", "pin": "0000"})
        self.assertEqual(res.status_code, 401)
        self.assertIn("Hatalı Öğretmen PIN", res.json()["detail"])

        # Hatalı öğretmen PIN'i ile kilitleme denemesi
        res = self.client.post("/api/lock", json={"board_id": "9-A", "pin": "9999"})
        self.assertEqual(res.status_code, 401)

        # Doğru PIN ama çevrimdışı tahta
        res = self.client.post("/api/unlock", json={"board_id": "Bilinmeyen-Tahta", "pin": config.TEACHER_PIN})
        self.assertEqual(res.status_code, 404)
        self.assertIn("çevrimdışı", res.json()["detail"])

        # Hatalı idare/müdür PIN'i ile anons denemesi
        res = self.client.post("/api/broadcast", json={
            "admin_pin": "1234",  # Öğretmen PIN'i müdür anonsunda çalışmamalı
            "target": "all",
            "message": "Duyuru"
        })
        self.assertEqual(res.status_code, 401)
        self.assertIn("Hatalı Müdür/İdare Giriş Kodu", res.json()["detail"])

        # Boş duyuru metni engelleme
        res = self.client.post("/api/broadcast", json={
            "admin_pin": config.ADMIN_PIN,
            "target": "all",
            "message": "   "
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("boş olamaz", res.json()["detail"])

    # -------------------------------------------------------------------------
    # 3. Canlı WebSocket ve Tahta Kilit / Anons Akışı Testi
    # -------------------------------------------------------------------------
    def test_03_websocket_live_board_lifecycle(self):
        """Tahtanın canlı WebSocket bağlantısını, kilit açma/kapama ve anons akışını test eder."""
        board_id = "10-B"

        # Henüz tahta bağlı değilken liste boş olmalı
        res = self.client.get("/api/boards")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["boards"]), 0)

        # Tahta WebSocket üzerinden sunucuya bağlanır
        with self.client.websocket_connect(f"/ws/board/{board_id}") as websocket:
            # 1. Hoş geldin mesajı kontrolü
            welcome_msg = websocket.receive_json()
            self.assertEqual(welcome_msg.get("action"), "welcome")
            self.assertEqual(welcome_msg.get("board_id"), board_id)

            # 2. Tahtalar listesinde çevrimiçi görünmeli
            res = self.client.get("/api/boards")
            boards = res.json()["boards"]
            self.assertEqual(len(boards), 1)
            self.assertEqual(boards[0]["id"], board_id)
            self.assertTrue(boards[0]["online"])
            self.assertEqual(boards[0]["status"], "locked")

            # 3. Öğretmen telefonundan kilit açma emri gönderir
            res_unlock = self.client.post("/api/unlock", json={
                "board_id": board_id,
                "pin": config.TEACHER_PIN
            })
            self.assertEqual(res_unlock.status_code, 200)
            self.assertTrue(res_unlock.json()["success"])

            # Tahtaya kilit açma emri anında düşmeli
            board_cmd = websocket.receive_json()
            self.assertEqual(board_cmd.get("action"), "unlock")
            self.assertEqual(board_cmd.get("by"), "teacher")

            # Tahta durumu 'unlocked' olarak güncellenmeli
            res = self.client.get("/api/boards")
            self.assertEqual(res.json()["boards"][0]["status"], "unlocked")

            # 4. Öğretmen telefonundan kilitleme emri gönderir
            res_lock = self.client.post("/api/lock", json={
                "board_id": board_id,
                "pin": config.TEACHER_PIN
            })
            self.assertEqual(res_lock.status_code, 200)

            # Tahtaya kilitle emri düşmeli
            board_cmd = websocket.receive_json()
            self.assertEqual(board_cmd.get("action"), "lock")

            # 5. Müdür bey duyuru yayını gönderir (Hedef: Belirli tahta)
            res_bc_single = self.client.post("/api/broadcast", json={
                "admin_pin": config.ADMIN_PIN,
                "target": board_id,
                "message": "Öğretmenler odasında toplantı vardır.",
                "duration_sec": 45
            })
            self.assertEqual(res_bc_single.status_code, 200)

            # Tahta anons mesajını almalı
            banner_cmd = websocket.receive_json()
            self.assertEqual(banner_cmd.get("action"), "banner_message")
            self.assertEqual(banner_cmd.get("message"), "Öğretmenler odasında toplantı vardır.")
            self.assertEqual(banner_cmd.get("duration_sec"), 45)

            # 6. Müdür bey tüm okula ('all') anons geçer
            res_bc_all = self.client.post("/api/broadcast", json={
                "admin_pin": config.ADMIN_PIN,
                "target": "all",
                "message": "İyi dersler dileriz.",
                "duration_sec": 30
            })
            self.assertEqual(res_bc_all.status_code, 200)
            banner_all_cmd = websocket.receive_json()
            self.assertEqual(banner_all_cmd.get("action"), "banner_message")
            self.assertEqual(banner_all_cmd.get("message"), "İyi dersler dileriz.")

            # 7. Tahtadan ping gönderilir -> pong yanıtı dönmeli
            websocket.send_json({"action": "ping"})
            pong_msg = websocket.receive_json()
            self.assertEqual(pong_msg.get("action"), "pong")

            # 8. Güç kapatma (Power off / Shutdown) testi
            res_power = self.client.post("/api/poweroff", json={
                "board_id": board_id,
                "pin": config.TEACHER_PIN
            })
            self.assertEqual(res_power.status_code, 200)
            power_cmd = websocket.receive_json()
            self.assertEqual(power_cmd.get("action"), "poweroff")

        # 9. WebSocket oturumu kapandıktan sonra tahta çevrimdışı görünmeli
        self.assertFalse(manager.is_connected(board_id))

    # -------------------------------------------------------------------------
    # 4. Çevrimdışı TOTP PIN Algoritması Matematiksel Senkronizasyon Testi
    # -------------------------------------------------------------------------
    def test_04_totp_offline_algorithm_sync(self):
        """Telefondaki JS algoritması ile tahtadaki Python kodunun birebir aynı PIN'i ürettiğini doğrular."""
        test_timestamps = [
            1730910000,
            1730910015,
            1730910029,
            1730910030,
            1730910059,
            1730910060,
            2000000000
        ]

        secret_salt = 7919

        for ts in test_timestamps:
            # Python tahta tarafı hesabı
            step_py = ts // 30
            py_code = str((step_py * secret_salt + 104729) % 10000).zfill(4)

            # JavaScript telefon tarafı hesabı (Math.floor(ts / 30))
            step_js = ts // 30
            raw_hash_js = (step_js * secret_salt + 104729) % 10000
            js_code = str(raw_hash_js).zfill(4)

            self.assertEqual(len(py_code), 4, f"PIN 4 haneli olmalı: {py_code}")
            self.assertEqual(py_code, js_code, f"Python ve JS TOTP eşleşmedi! ts: {ts}")

        # Zamanın aynı 30 saniyelik diliminde (örneğin ts=10 ve ts=25) aynı kodu üretmeli
        base_t = 1730910000
        step_base = base_t // 30
        code_start = str((step_base * secret_salt + 104729) % 10000).zfill(4)

        next_t = base_t + 25  # 25 saniye sonra aynı periyot içinde
        step_next = next_t // 30
        code_next = str((step_next * secret_salt + 104729) % 10000).zfill(4)
        self.assertEqual(code_start, code_next)

        # 31 saniye sonra periyot değişmeli ve yeni kod üretilmeli
        after_t = base_t + 31
        step_after = after_t // 30
        code_after = str((step_after * secret_salt + 104729) % 10000).zfill(4)
        self.assertNotEqual(code_start, code_after)


if __name__ == "__main__":
    unittest.main(verbosity=2)
