// -------------------------------------------------------------
// 📱 ETAP Akıllı Kilit & Mobil Yönetim İstemci Scripti
// -------------------------------------------------------------

let html5QrCode = null;
let isScanning = false;
let totpInterval = null;

// Sayfa yüklendiğinde
document.addEventListener("DOMContentLoaded", () => {
  // Kayıtlı PIN'leri ve son seçilen tahtayı yükle
  const savedPin = localStorage.getItem("etap_teacher_pin");
  if (savedPin) {
    document.getElementById("teacherPin").value = savedPin;
  }
  const savedBoard = localStorage.getItem("etap_selected_board");
  if (savedBoard) {
    document.getElementById("customBoardInput").value = savedBoard;
  }

  // Çevrimiçi tahtaları listele
  fetchOnlineBoards();

  // Çevrimdışı TOTP sayacını başlat
  startTotpGenerator();
});

// -------------------------------------------------------------
// 📑 Sekme Değiştirme
// -------------------------------------------------------------
function switchTab(tabName) {
  document.querySelectorAll(".tab-btn").forEach(btn => btn.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach(content => content.classList.remove("active"));

  if (tabName === "teacher") {
    document.querySelector(".tab-btn:nth-child(1)").classList.add("active");
    document.getElementById("teacherTab").classList.add("active");
  } else if (tabName === "offline") {
    document.querySelector(".tab-btn:nth-child(2)").classList.add("active");
    document.getElementById("offlineTab").classList.add("active");
  } else if (tabName === "admin") {
    document.querySelector(".tab-btn:nth-child(3)").classList.add("active");
    document.getElementById("adminTab").classList.add("active");
  }

  // Kamera açıksa ve başka sekmeye geçildiyse kapat
  if (tabName !== "teacher" && isScanning) {
    stopCameraScanner();
  }
}

// -------------------------------------------------------------
// 📡 Çevrimiçi Tahtaları Listeleme (Sadece Aktif Tahtalar)
// -------------------------------------------------------------
async function fetchOnlineBoards() {
  const select = document.getElementById("boardSelect");
  const adminTarget = document.getElementById("adminTarget");

  try {
    const res = await fetch("/api/boards?online_only=true");
    const data = await res.json();

    if (data.success && data.boards) {
      select.innerHTML = '<option value="">-- Çevrimiçi Tahta Seçin --</option>';
      adminTarget.innerHTML = '<option value="all">📢 TÜM OKUL (Tüm Tahtalar)</option>';

      // Sadece ve sadece çevrimiçi (online) tahtaları göster
      const onlineBoards = data.boards.filter(b => b.online);

      if (onlineBoards.length === 0) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "⚠️ Şu an açık tahta yok";
        select.appendChild(opt);
      } else {
        onlineBoards.forEach(b => {
          const statusEmoji = b.status === "unlocked" ? "🔓" : "🔒";
          const displayName = b.name || b.id;
          const opt = document.createElement("option");
          opt.value = b.id;
          opt.textContent = `${statusEmoji} ${displayName}`;
          select.appendChild(opt);

          // Müdür paneli için hedef
          const adminOpt = document.createElement("option");
          adminOpt.value = b.id;
          adminOpt.textContent = `🖥️ ${displayName}`;
          adminTarget.appendChild(adminOpt);
        });
      }
    }
  } catch (err) {
    console.warn("Sunucuya bağlanılamadı veya çevrimdışı:", err);
  }
}

async function cleanupOfflineBoards() {
  try {
    const res = await fetch("/api/boards/cleanup", { method: "POST" });
    const data = await res.json();
    showToast(data.message || "Temizlendi", "success");
    fetchOnlineBoards();
  } catch (e) {
    showToast("Temizleme sırasında hata oluştu", "error");
  }
}

function onBoardSelectChange() {
  const select = document.getElementById("boardSelect");
  if (select.value) {
    document.getElementById("customBoardInput").value = select.value;
    localStorage.setItem("etap_selected_board", select.value);
  }
}

// Seçili Tahta ID'sini Al
function getSelectedBoardId() {
  const customInput = document.getElementById("customBoardInput");
  const targetId = customInput.dataset.targetId;
  const custom = customInput.value.trim();
  const select = document.getElementById("boardSelect").value;
  return targetId || custom || select;
}

// -------------------------------------------------------------
// 📷 Kamera QR Okuyucu
// -------------------------------------------------------------
async function toggleCameraScanner() {
  if (isScanning) {
    stopCameraScanner();
  } else {
    startCameraScanner();
  }
}

async function startCameraScanner() {
  const qrDiv = document.getElementById("qrReader");
  const btn = document.getElementById("startScanBtn");

  qrDiv.classList.remove("hidden");
  btn.textContent = "🛑 Taramayı Durdur";
  isScanning = true;

  html5QrCode = new Html5Qrcode("qrReader");
  const config = { fps: 10, qrbox: { width: 220, height: 220 } };

  try {
    await html5QrCode.start(
      { facingMode: "environment" },
      config,
      (decodedText) => {
        // QR okundu!
        onQrCodeSuccess(decodedText);
      },
      (error) => {
        // Okuma anlık başarısız, sessizce devam et
      }
    );
  } catch (err) {
    showToast("Kamera açılamadı: " + err, "error");
    stopCameraScanner();
  }
}

async function stopCameraScanner() {
  if (html5QrCode && isScanning) {
    try {
      await html5QrCode.stop();
      html5QrCode.clear();
    } catch (e) {}
  }
  document.getElementById("qrReader").classList.add("hidden");
  document.getElementById("startScanBtn").textContent = "📷 Tahtadaki QR Kodu Tara";
  isScanning = false;
}

function onQrCodeSuccess(decodedText) {
  // Titreşim desteği (hissedilebilir başarı geri bildirimi)
  if (navigator.vibrate) navigator.vibrate(100);

  stopCameraScanner();

  try {
    if (decodedText.startsWith("etap://")) {
      const url = new URL(decodedText);
      const boardId = url.searchParams.get("board");
      const boardName = url.searchParams.get("name") || boardId;
      if (boardId) {
        const input = document.getElementById("customBoardInput");
        input.value = boardName;
        input.dataset.targetId = boardId;
        localStorage.setItem("etap_selected_board", boardName);
      }
    } else {
      const input = document.getElementById("customBoardInput");
      input.value = decodedText;
      delete input.dataset.targetId;
      localStorage.setItem("etap_selected_board", decodedText);
    }
  } catch (e) {
    const input = document.getElementById("customBoardInput");
    input.value = decodedText;
    delete input.dataset.targetId;
  }

  showToast("Tahta algılandı! Açılıyor...", "success");

  // Otomatik Kilidi Açmayı Tetikle
  sendUnlock();
}

// -------------------------------------------------------------
// 🔓 Kilidi Aç & 🔒 Kilitle İstekleri
// -------------------------------------------------------------
async function sendUnlock() {
  const boardId = getSelectedBoardId();
  const pin = document.getElementById("teacherPin").value.trim();

  if (!boardId) {
    showToast("Lütfen bir sınıf/tahta seçin veya QR okutun!", "error");
    return;
  }
  if (!pin) {
    showToast("Lütfen Ortak Öğretmen PIN Kodunu girin!", "error");
    return;
  }

  localStorage.setItem("etap_teacher_pin", pin);
  localStorage.setItem("etap_selected_board", boardId);

  const btn = document.getElementById("unlockBtn");
  btn.disabled = true;
  btn.textContent = "⏳ Açılıyor...";

  try {
    const res = await fetch("/api/unlock", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ board_id: boardId, pin: pin })
    });
    const data = await res.json();

    if (res.ok && data.success) {
      showToast(data.message, "success");
      if (navigator.vibrate) navigator.vibrate([100, 50, 100]);
    } else {
      showToast(data.detail || "Kilit açılamadı!", "error");
    }
  } catch (err) {
    showToast("Sunucuya ulaşılamadı! İnternet yoksa 'Çevrimdışı PIN' sekmesini kullanın.", "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "🔓 Kilidi Aç";
    fetchOnlineBoards();
  }
}

async function sendLock() {
  const boardId = getSelectedBoardId();
  const pin = document.getElementById("teacherPin").value.trim();

  if (!boardId || !pin) {
    showToast("Lütfen tahta ve PIN kodunu girin!", "error");
    return;
  }

  const btn = document.getElementById("lockBtn");
  btn.disabled = true;
  btn.textContent = "⏳ Kilitleniyor...";

  try {
    const res = await fetch("/api/lock", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ board_id: boardId, pin: pin })
    });
    const data = await res.json();

    if (res.ok && data.success) {
      showToast(data.message, "success");
    } else {
      showToast(data.detail || "Hata oluştu!", "error");
    }
  } catch (err) {
    showToast("Sunucuya ulaşılamadı!", "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "🔒 Dersi Bitir & Kilitle";
    fetchOnlineBoards();
  }
}

// -------------------------------------------------------------
// ⚡ Tahtayı Kapatma (Güç Kapatma / Shutdown)
// -------------------------------------------------------------
function confirmPoweroff() {
  const boardId = getSelectedBoardId();
  const pin = document.getElementById("teacherPin").value.trim();

  if (!boardId) {
    showToast("Lütfen kapatılacak tahtayı seçin!", "error");
    return;
  }
  if (!pin) {
    showToast("Lütfen yetkili PIN kodunuzu girin!", "error");
    return;
  }

  const modal = document.getElementById("powerModal");
  const modalDesc = document.getElementById("modalDesc");
  const displayName = document.getElementById("customBoardInput").value || boardId;

  modalDesc.textContent = `'${displayName}' akıllı tahtası tamamen kapatılacaktır. Tahta üzerindeki tüm pencereler kapanacaktır. Devam etmek istiyor musunuz?`;
  modal.classList.remove("hidden");
}

function closePowerModal() {
  document.getElementById("powerModal").classList.add("hidden");
}

async function sendPoweroff() {
  const boardId = getSelectedBoardId();
  const pin = document.getElementById("teacherPin").value.trim();
  const confirmBtn = document.getElementById("modalConfirmBtn");

  closePowerModal();

  if (!boardId || !pin) {
    showToast("Tahta ve PIN kodu gereklidir!", "error");
    return;
  }

  showToast("Tahtaya kapatma komutu iletiliyor...", "info");

  try {
    const res = await fetch("/api/poweroff", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ board_id: boardId, pin: pin })
    });
    const data = await res.json();

    if (res.ok && data.success) {
      showToast(data.message, "success");
      if (navigator.vibrate) navigator.vibrate([200, 100, 200]);
    } else {
      showToast(data.detail || "Kapatma komutu gönderilemedi!", "error");
    }
  } catch (err) {
    showToast("Sunucuya ulaşılamadı!", "error");
  } finally {
    setTimeout(fetchOnlineBoards, 3000);
  }
}

// -------------------------------------------------------------
// 📢 Müdür / İdare Duyuru Yayını
// -------------------------------------------------------------
async function sendBroadcast() {
  const adminPin = document.getElementById("adminPin").value.trim();
  const target = document.getElementById("adminTarget").value;
  const message = document.getElementById("adminMessage").value.trim();
  const duration = parseInt(document.getElementById("adminDuration").value) || 60;

  if (!adminPin) {
    showToast("Lütfen İdare PIN kodunu girin!", "error");
    return;
  }
  if (!message) {
    showToast("Lütfen bir duyuru metni yazın!", "error");
    return;
  }

  try {
    const res = await fetch("/api/broadcast", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        admin_pin: adminPin,
        target: target,
        message: message,
        duration_sec: duration
      })
    });
    const data = await res.json();

    if (res.ok && data.success) {
      showToast(data.message, "success");
      document.getElementById("adminMessage").value = "";
    } else {
      showToast(data.detail || "Duyuru iletilemedi!", "error");
    }
  } catch (err) {
    showToast("Sunucu hatası: " + err, "error");
  }
}

// -------------------------------------------------------------
// 🔢 Çevrimdışı TOTP (Zaman Tabanlı Geçici Şifre Algoritması)
// -------------------------------------------------------------
function startTotpGenerator() {
  updateTotpCode();
  setInterval(updateTotpCode, 1000);
}

function updateTotpCode() {
  const now = Math.floor(Date.now() / 1000);
  const period = 30; // 30 saniyelik periyot
  const step = Math.floor(now / period);
  const remainingSec = period - (now % period);

  // Basit ve deterministik saat bazlı 4 haneli PIN üretici (İnternetsiz)
  // Tahtadaki Python koduyla birebir aynı matematiksel formülü kullanır:
  const secretSalt = 7919; // Ortak asal sayı
  const rawHash = (step * secretSalt + 104729) % 10000;
  const pinCode = rawHash.toString().padStart(4, "0");

  const codeEl = document.getElementById("totpCode");
  const barEl = document.getElementById("totpBar");
  const secEl = document.getElementById("totpSec");

  if (codeEl) codeEl.textContent = pinCode;
  if (barEl) barEl.style.width = `${(remainingSec / period) * 100}%`;
  if (secEl) secEl.textContent = `${remainingSec} saniye sonra değişecek`;
}

// -------------------------------------------------------------
// 🔔 Bildirim Toast'ı
// -------------------------------------------------------------
function showToast(text, type = "info") {
  const toast = document.getElementById("toast");
  toast.textContent = text;
  toast.className = `toast ${type}`;
  toast.classList.remove("hidden");

  setTimeout(() => {
    toast.classList.add("hidden");
  }, 3500);
}
