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
  const savedAdminPin = localStorage.getItem("etap_admin_pin");
  if (savedAdminPin && document.getElementById("adminPin")) {
    document.getElementById("adminPin").value = savedAdminPin;
  }

  // Çevrimiçi tahtaları listele
  fetchOnlineBoards();

  // Merkezi okul/kurum adını yükle
  fetchSchoolName();

  // Çevrimdışı TOTP sayacını başlat
  startTotpGenerator();

  // PWA (Mobil Uygulama) Desteğini Başlat
  setupPwa();
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
    fetchAdminFleet();
    fetchSchoolName();
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

      // Canlı Filo Listesini Güncelle
      renderAdminBoardFleet(onlineBoards);
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
// 🏫 Okul / Kurum Adı Yönetimi (Merkezi Yayın)
// -------------------------------------------------------------
async function fetchSchoolName() {
  try {
    const res = await fetch("/api/settings/school");
    if (res.ok) {
      const data = await res.json();
      const input = document.getElementById("schoolNameInput");
      if (input && data.school_name) {
        input.value = data.school_name;
      }
    }
  } catch (e) {
    console.log("Kurum adı çekilemedi:", e);
  }
}

async function sendSchoolNameUpdate() {
  const adminPin = document.getElementById("adminPin").value.trim();
  const schoolName = document.getElementById("schoolNameInput").value.trim();

  if (!adminPin) {
    showToast("Lütfen İdare Giriş Kodunu girin!", "error");
    document.getElementById("adminPin").focus();
    return;
  }
  if (!schoolName) {
    showToast("Lütfen Okul / Kurum adını yazın!", "error");
    return;
  }

  // Pin'i sonraki işlemler için kaydet
  localStorage.setItem("etap_admin_pin", adminPin);

  try {
    const res = await fetch("/api/settings/school", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        admin_pin: adminPin,
        school_name: schoolName
      })
    });
    const data = await res.json();

    if (res.ok && data.success) {
      showToast(data.message, "success");
    } else {
      showToast(data.detail || "Kurum adı güncellenemedi!", "error");
    }
  } catch (err) {
    showToast("Sunucu hatası: " + err, "error");
  }
}

// -------------------------------------------------------------
// 🖥️ Canlı Tahta Filosu & Uzaktan Ekran Görüntüsü
// -------------------------------------------------------------
let currentScreenshotBoard = null;

async function fetchAdminFleet() {
  const container = document.getElementById("adminFleetContainer");
  if (container) {
    container.innerHTML = '<div style="text-align:center; padding:15px; color:#38bdf8;"><div class="spinner"></div><div style="margin-top:8px;">Tahtalar taranıyor...</div></div>';
  }
  await fetchOnlineBoards();
}

function renderAdminBoardFleet(boards) {
  const container = document.getElementById("adminFleetContainer");
  if (!container) return;

  if (!boards || boards.length === 0) {
    container.innerHTML = `
      <div style="text-align:center; padding:18px; color:#94a3b8; font-size:0.88rem;">
        ⚠️ Şu anda açık ve çevrimiçi olan akıllı tahta bulunmuyor.
      </div>
    `;
    return;
  }

  container.innerHTML = "";
  boards.forEach(b => {
    const isUnlocked = b.status === "unlocked";
    const statusText = isUnlocked ? "🟢 Açık (Derste)" : "🔒 Kilitli (Beklemede)";
    const statusClass = isUnlocked ? "online-unlocked" : "online-locked";
    const displayName = b.name || b.id;

    const card = document.createElement("div");
    card.className = "fleet-card";
    card.innerHTML = `
      <div class="fleet-info">
        <span class="fleet-name">🖥️ ${escapeHtml(displayName)}</span>
        <span class="fleet-status ${statusClass}">${statusText}</span>
      </div>
      <div class="fleet-actions">
        <button type="button" class="btn-screenshot" onclick="openScreenshotModal('${escapeHtml(b.id)}', '${escapeHtml(displayName)}')">
          📸 Ekranı Gör
        </button>
      </div>
    `;
    container.appendChild(card);
  });
}

async function openScreenshotModal(boardId, boardName) {
  const adminPin = document.getElementById("adminPin").value.trim();
  if (!adminPin) {
    showToast("Lütfen yukarıdaki İdare Giriş Kodunu giriniz!", "error");
    document.getElementById("adminPin").focus();
    return;
  }

  currentScreenshotBoard = { id: boardId, name: boardName };

  const modal = document.getElementById("screenshotModal");
  const title = document.getElementById("screenshotBoardTitle");
  const loading = document.getElementById("screenshotLoading");
  const wrapper = document.getElementById("screenshotImgWrapper");

  title.textContent = `📸 ${boardName} — Canlı Ekran`;
  loading.classList.remove("hidden");
  wrapper.classList.add("hidden");
  modal.classList.remove("hidden");

  await requestBoardScreenshot(boardId, adminPin);
}

async function refreshCurrentScreenshot() {
  if (!currentScreenshotBoard) return;
  const adminPin = document.getElementById("adminPin").value.trim();
  const loading = document.getElementById("screenshotLoading");
  const wrapper = document.getElementById("screenshotImgWrapper");

  loading.classList.remove("hidden");
  wrapper.classList.add("hidden");

  await requestBoardScreenshot(currentScreenshotBoard.id, adminPin);
}

async function requestBoardScreenshot(boardId, adminPin) {
  const loading = document.getElementById("screenshotLoading");
  const wrapper = document.getElementById("screenshotImgWrapper");
  const img = document.getElementById("screenshotImg");
  const timeEl = document.getElementById("screenshotTimestamp");

  try {
    const res = await fetch("/api/board/screenshot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ board_id: boardId, admin_pin: adminPin })
    });
    const data = await res.json();

    if (res.ok && data.success && data.image) {
      img.src = data.image;
      const d = new Date(data.timestamp * 1000);
      timeEl.textContent = `🕒 Çekilme Saati: ${d.toLocaleTimeString("tr-TR")}`;
      loading.classList.add("hidden");
      wrapper.classList.remove("hidden");
    } else {
      loading.classList.add("hidden");
      showToast(data.detail || "Ekran görüntüsü alınamadı!", "error");
      closeScreenshotModal();
    }
  } catch (err) {
    loading.classList.add("hidden");
    showToast("Sunucu bağlantı hatası: " + err, "error");
    closeScreenshotModal();
  }
}

function closeScreenshotModal() {
  const modal = document.getElementById("screenshotModal");
  if (modal) modal.classList.add("hidden");
}

// -------------------------------------------------------------
// ⚡ Toplu Yönetim Aksiyonları
// -------------------------------------------------------------
async function triggerBulkAction(action) {
  const adminPin = document.getElementById("adminPin").value.trim();
  if (!adminPin) {
    showToast("Lütfen önce yukarıdaki İdare Giriş Kodunu giriniz!", "error");
    document.getElementById("adminPin").focus();
    return;
  }

  const endpointMap = {
    lock: "/api/bulk/lock",
    unlock: "/api/bulk/unlock",
    poweroff: "/api/bulk/poweroff"
  };

  if (action === "unlock" && !confirm("⚠️ DİKKAT: Okuldaki tüm akıllı tahtaların kilidi AÇILACAKTIR!\n\nOnaylıyor musunuz?")) {
    return;
  }

  try {
    const res = await fetch(endpointMap[action], {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ admin_pin: adminPin })
    });
    const data = await res.json();

    if (res.ok && data.success) {
      showToast(data.message, "success");
      fetchOnlineBoards();
    } else {
      showToast(data.detail || "İşlem gerçekleştirilemedi!", "error");
    }
  } catch (err) {
    showToast("Sunucu hatası: " + err, "error");
  }
}

function confirmBulkPoweroff() {
  const adminPin = document.getElementById("adminPin").value.trim();
  if (!adminPin) {
    showToast("Lütfen önce yukarıdaki İdare Giriş Kodunu giriniz!", "error");
    document.getElementById("adminPin").focus();
    return;
  }

  if (confirm("🛑 DİKKAT: Okuldaki açık olan TÜM akıllı tahtalar tamamen kapatılacaktır (shutdown)!\n\nDevam etmek istiyor musunuz?")) {
    triggerBulkAction("poweroff");
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
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

// -------------------------------------------------------------
// 📱 PWA & Mobil Uygulama Kurulum Yöneticisi
// -------------------------------------------------------------
let deferredInstallPrompt = null;

function setupPwa() {
  // 1. Service Worker Kaydı (Çevrimdışı önbellek ve PWA kabiliyeti)
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js")
        .then((reg) => {
          console.log("📦 ServiceWorker başarıyla devrede:", reg.scope);
        })
        .catch((err) => {
          console.warn("⚠️ ServiceWorker kaydı:", err);
        });
    });
  }

  // 2. Uygulama zaten standalone modunda açılmışsa bildirimleri gizle
  const isStandalone = window.matchMedia("(display-mode: standalone)").matches || 
                       window.navigator.standalone === true;
  if (isStandalone) {
    console.log("📱 Uygulama tam ekran standalone modunda çalışıyor.");
    return;
  }

  // 3. Android / Chrome: 'Uygulamayı Yükle' tetikleyicisini dinle
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredInstallPrompt = e;
    const banner = document.getElementById("pwaInstallBanner");
    if (banner && !sessionStorage.getItem("pwa_dismissed")) {
      banner.classList.remove("hidden");
    }
  });

  const installBtn = document.getElementById("pwaInstallBtn");
  if (installBtn) {
    installBtn.addEventListener("click", async () => {
      if (deferredInstallPrompt) {
        deferredInstallPrompt.prompt();
        const { outcome } = await deferredInstallPrompt.userChoice;
        console.log("Kullanıcı yükleme tercihi:", outcome);
        deferredInstallPrompt = null;
        dismissPwaBanner();
      }
    });
  }

  // 4. iOS (iPhone Safari) Tespiti ve Rehber Gösterimi
  const userAgent = window.navigator.userAgent.toLowerCase();
  const isIos = /iphone|ipad|ipod/.test(userAgent);
  const isSafari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent);

  if (isIos && isSafari && !isStandalone && !sessionStorage.getItem("ios_guide_dismissed")) {
    const iosGuide = document.getElementById("iosInstallGuide");
    if (iosGuide) {
      setTimeout(() => {
        iosGuide.classList.remove("hidden");
      }, 1200);
    }
  }
}

function dismissPwaBanner() {
  const banner = document.getElementById("pwaInstallBanner");
  if (banner) banner.classList.add("hidden");
  sessionStorage.setItem("pwa_dismissed", "true");
}

function dismissIosGuide() {
  const guide = document.getElementById("iosInstallGuide");
  if (guide) guide.classList.add("hidden");
  sessionStorage.setItem("ios_guide_dismissed", "true");
}
