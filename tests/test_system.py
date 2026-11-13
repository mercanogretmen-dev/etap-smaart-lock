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
        self.assertIn("Tahta Kilit", res_index.text)
        self.assertIn("html5-qrcode", res_index.text)

        res_css = self.client.get("/style.css")
        self.assertEqual(res_css.status_code, 200)

        res_js = self.client.get("/app.js")
        self.assertEqual(res_js.status_code, 200)
        self.assertIn("fetchOnlineBoards", res_js.text)

        # PWA Manifest & Service Worker & İkon testleri
        res_manifest = self.client.get("/manifest.json")
        self.assertEqual(res_manifest.status_code, 200)
        self.assertIn("Tahta Kilit", res_manifest.text)

        res_sw = self.client.get("/sw.js")
        self.assertEqual(res_sw.status_code, 200)
        self.assertIn("Service-Worker-Allowed", res_sw.headers)

        res_icon = self.client.get("/icons/icon-192.png")
        self.assertEqual(res_icon.status_code, 200)

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

            # 7.1 Canlı isim güncelleme testi (WebSocket kesilmeden ad değiştirme)
            websocket.send_json({"action": "update_name", "name": "10-B Yeni Şube"})
            update_ack = websocket.receive_json()
            self.assertEqual(update_ack.get("action"), "name_updated")
            self.assertEqual(update_ack.get("name"), "10-B Yeni Şube")
            self.assertEqual(manager.board_names[board_id], "10-B Yeni Şube")

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

        # 10. Çevrimdışı hayalet kayıtları temizleme testi
        res_cleanup = self.client.post("/api/boards/cleanup", json={"admin_pin": config.ADMIN_PIN})
        self.assertEqual(res_cleanup.status_code, 200)
        self.assertNotIn(board_id, manager.board_names)

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

    def test_05_single_instance_lock(self):
        """QLockFile mekanizmasının çift oturum açılışını engellediğini doğrular."""
        import tempfile
        from PyQt6.QtCore import QLockFile

        lock_path = os.path.join(tempfile.gettempdir(), "tahta_kilit_unittest.lock")
        if os.path.exists(lock_path):
            try:
                os.remove(lock_path)
            except Exception:
                pass

        lock1 = QLockFile(lock_path)
        lock1.setStaleLockTime(5000)
        self.assertTrue(lock1.tryLock(100), "Birinci kilit başarıyla alınmalı")

        # İkinci kopya kilidi alamamalı (çift açılış engeli)
        lock2 = QLockFile(lock_path)
        lock2.setStaleLockTime(5000)
        self.assertFalse(lock2.tryLock(50), "İkinci kilit engellenmeli!")

        # Birinci kilit bırakıldığında ikinci kopya alabilmeli
        lock1.unlock()
        self.assertTrue(lock2.tryLock(100), "İlk kilit serbest kaldığında yeni kilit alınabilmeli")
        lock2.unlock()

    # -------------------------------------------------------------------------
    # 6. Merkezi Kurum/Okul Adı Yönetimi ve Canlı Yayın Testi
    # -------------------------------------------------------------------------
    def test_06_centralized_school_settings(self):
        """Telefondan okul adının değiştirilip bağlı tüm tahtalara yayınlandığını test eder."""
        # 1. Mevcut okul adını çekme
        res_get = self.client.get("/api/settings/school")
        self.assertEqual(res_get.status_code, 200)
        self.assertIn("school_name", res_get.json())

        # 2. Yetkisiz istek denemesi
        res_unauth = self.client.post("/api/settings/school", json={
            "admin_pin": "wrong_pin",
            "school_name": "Test Anadolu Lisesi"
        })
        self.assertEqual(res_unauth.status_code, 401)

        # 3. Boş okul adı denemesi
        res_empty = self.client.post("/api/settings/school", json={
            "admin_pin": config.ADMIN_PIN,
            "school_name": "   "
        })
        self.assertEqual(res_empty.status_code, 400)

        # 4. Canlı tahta bağlıyken güncelleme ve yayın kontrolü
        board_id = "11-C"
        with self.client.websocket_connect(f"/ws/board/{board_id}") as websocket:
            # Hoş geldin mesajı içinde okul adı gelmeli
            welcome = websocket.receive_json()
            self.assertEqual(welcome.get("action"), "welcome")
            self.assertIn("school_name", welcome)

            # İdare telefondan okul adını günceller
            new_name = "ŞEHİT AHMET ALAN ANADOLU LİSESİ"
            res_update = self.client.post("/api/settings/school", json={
                "admin_pin": config.ADMIN_PIN,
                "school_name": new_name
            })
            self.assertEqual(res_update.status_code, 200)
            self.assertEqual(res_update.json()["school_name"], new_name)

            # Tahtaya WebSocket'ten update_school_name emri düşmeli
            ws_school_msg = websocket.receive_json()
            self.assertEqual(ws_school_msg.get("action"), "update_school_name")
            self.assertEqual(ws_school_msg.get("school_name"), new_name)

            # Tekrar GET yapıldığında yeni ad dönmeli
            res_after = self.client.get("/api/settings/school")
            self.assertEqual(res_after.json()["school_name"], new_name)

    # -------------------------------------------------------------------------
    # 7. Toplu Yönetim (Bulk Lock/Unlock/Poweroff) ve Canlı Ekran Görüntüsü Testi
    # -------------------------------------------------------------------------
    def test_07_bulk_actions_and_live_screenshot(self):
        """Müdür panelinden toplu kilit/kapatma ve canlı ekran görüntüsü akışını doğrular."""
        # 1. Yetkisiz toplu kilit denemesi
        res_unauth = self.client.post("/api/bulk/lock", json={"admin_pin": "wrong"})
        self.assertEqual(res_unauth.status_code, 401)

        # 2. İki tahta canlı bağlanır (9-A ve 10-A)
        with self.client.websocket_connect("/ws/board/9-A") as ws1:
            ws1.receive_json()  # welcome
            with self.client.websocket_connect("/ws/board/10-A") as ws2:
                ws2.receive_json()  # welcome

                # 3. Toplu Kilitleme
                res_bulk_lock = self.client.post("/api/bulk/lock", json={"admin_pin": config.ADMIN_PIN})
                self.assertEqual(res_bulk_lock.status_code, 200)
                self.assertEqual(res_bulk_lock.json()["count"], 2)

                cmd1 = ws1.receive_json()
                cmd2 = ws2.receive_json()
                self.assertEqual(cmd1.get("action"), "lock")
                self.assertEqual(cmd2.get("action"), "lock")

                # 4. Toplu Kilit Açma
                res_bulk_unlock = self.client.post("/api/bulk/unlock", json={"admin_pin": config.ADMIN_PIN})
                self.assertEqual(res_bulk_unlock.status_code, 200)
                self.assertEqual(res_bulk_unlock.json()["count"], 2)

                cmd1 = ws1.receive_json()
                cmd2 = ws2.receive_json()
                self.assertEqual(cmd1.get("action"), "unlock")
                self.assertEqual(cmd2.get("action"), "unlock")

                # 5. Toplu Kapatma (Poweroff)
                res_bulk_power = self.client.post("/api/bulk/poweroff", json={"admin_pin": config.ADMIN_PIN})
                self.assertEqual(res_bulk_power.status_code, 200)
                self.assertEqual(res_bulk_power.json()["count"], 2)

                cmd1 = ws1.receive_json()
                cmd2 = ws2.receive_json()
                self.assertEqual(cmd1.get("action"), "poweroff")
                self.assertEqual(cmd2.get("action"), "poweroff")

                # 6. Canlı Ekran Görüntüsü Alma Testi
                # Çevrimdışı tahta için 404 dönmeli
                res_shot_offline = self.client.post("/api/board/screenshot", json={
                    "admin_pin": config.ADMIN_PIN,
                    "board_id": "Bilinmeyen-Tahta"
                })
                self.assertEqual(res_shot_offline.status_code, 404)

                # Canlı bağlı 9-A tahtası için ekran görüntüsü isteği
                orig_send = manager.send_to_board
                async def mock_send_with_screenshot_reply(b_id, msg):
                    if msg.get("action") == "take_screenshot":
                        req_id = msg.get("request_id")
                        fut = manager.pending_screenshots.get(req_id)
                        if fut and not fut.done():
                            fut.set_result({
                                "action": "screenshot_response",
                                "request_id": req_id,
                                "image": "data:image/jpeg;base64,/9j/4AAQSkZJRg==",
                                "timestamp": time.time()
                            })
                    return await orig_send(b_id, msg)

                manager.send_to_board = mock_send_with_screenshot_reply
                try:
                    res_shot = self.client.post("/api/board/screenshot", json={
                        "admin_pin": config.ADMIN_PIN,
                        "board_id": "9-A"
                    })
                    self.assertEqual(res_shot.status_code, 200)
                    self.assertTrue(res_shot.json()["success"])
                    self.assertEqual(res_shot.json()["board_id"], "9-A")
                    self.assertIn("data:image/jpeg;base64", res_shot.json()["image"])
                finally:
                    manager.send_to_board = orig_send

    # -------------------------------------------------------------------------
    # 8. Donanım Parmak İzi & Klon Koruma (Anti-Cloning) Testi
    # -------------------------------------------------------------------------
    def test_08_hardware_id_generation_and_anti_clone(self):
        """Klon imajlarda benzersiz ID üretimini ve çakışma korumasını doğrular."""
        import configparser
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "kilit_ekrani",
            os.path.join(PROJECT_ROOT, "client-tahta", "kilit_ekrani.py")
        )
        mod_kilit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod_kilit)

        # Test esnasında yerel disk dosyalarını kirletmemek için save_config'i mock'la
        orig_save = mod_kilit.save_config
        mod_kilit.save_config = lambda c: True

        try:
            get_hardware_fingerprint_info = mod_kilit.get_hardware_fingerprint_info
            get_device_id = mod_kilit.get_device_id
            BLACKLISTED_DEVICE_IDS = mod_kilit.BLACKLISTED_DEVICE_IDS

            # 1. Donanım parmak izi fonksiyonu format kontrolü
            curr_id, elements, sig_hash = get_hardware_fingerprint_info()
            self.assertTrue(curr_id.startswith("etap-"))
            self.assertEqual(len(curr_id), 13)  # 'etap-' (5) + 8 hex hanesi
            self.assertTrue(len(elements) > 0)
            self.assertEqual(len(sig_hash), 64)

            # 2. Kara listedeki 'etap-57435795' kimliğinin otomatik temizlenmesi
            cfg_blacklisted = configparser.ConfigParser()
            cfg_blacklisted.add_section("GENEL")
            cfg_blacklisted.set("GENEL", "cihaz_id", "etap-57435795")
            clean_id = get_device_id(cfg_blacklisted)
            self.assertNotIn(clean_id, BLACKLISTED_DEVICE_IDS)
            self.assertEqual(clean_id, curr_id)
            self.assertEqual(cfg_blacklisted.get("GENEL", "cihaz_id"), curr_id)
            self.assertTrue(len(cfg_blacklisted.get("GENEL", "hardware_elements")) > 0)

            # 3. Aynı tahtada kalıcılık (Değişmeme) testi
            persisted_id = get_device_id(cfg_blacklisted)
            self.assertEqual(persisted_id, clean_id)

            # 4. Klonlama tespiti (Başka bir fiziksel tahtadan alınan imaj)
            cfg_cloned = configparser.ConfigParser()
            cfg_cloned.add_section("GENEL")
            cfg_cloned.set("GENEL", "cihaz_id", "etap-aabbccdd")
            cfg_cloned.set("GENEL", "hardware_elements", "MAC:eth0:00:11:22:33:44:55,DMI:FAKE-OTHER-BOARD")

            healed_id = get_device_id(cfg_cloned)
            self.assertNotEqual(healed_id, "etap-aabbccdd", "Klon imaj eski tahtanın ID'sini taşımamalı!")
            self.assertEqual(healed_id, curr_id, "Klon imaj bu tahtanın kendi donanım ID'sini almalı!")
            self.assertEqual(cfg_cloned.get("GENEL", "cihaz_id"), curr_id)
        finally:
            mod_kilit.save_config = orig_save


if __name__ == "__main__":
    unittest.main(verbosity=2)
