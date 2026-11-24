// -------------------------------------------------------------
// 📱 ETAP Akıllı Kilit & Mobil Yönetim İstemci Scripti
// -------------------------------------------------------------

let html5QrCode = null;
let isScanning = false;
let totpInterval = null;
let cachedOnlineBoards = [];
let selectedBoard = { id: "", name: "", status: "" };

// Sayfa yüklendiğinde
document.addEventListener("DOMContentLoaded", () => {
  // Kayıtlı PIN'leri ve son seçilen tahtayı yükle
  const savedPin = localStorage.getItem("etap_teacher_pin");
  if (savedPin) {
    document.getElementById("teacherPin").value = savedPin;
    updateTeacherPinUI(false);
  } else {
    updateTeacherPinUI(true);
  }

  const savedBoardId = localStorage.getItem("etap_selected_board");
  const savedBoardName = localStorage.getItem("etap_selected_board_name");
  if (savedBoardId) {
    selectedBoard = {
      id: savedBoardId,
      name: savedBoardName || savedBoardId,
      status: ""
    };
  }
  updateSelectedBoardBadge();

  const savedAdminPin = localStorage.getItem("etap_admin_pin");
  if (savedAdminPin) {
    if (document.getElementById("adminPin")) {
      document.getElementById("adminPin").value = savedAdminPin;
    }
    if (document.getElementById("fleetAdminPin")) {
      document.getElementById("fleetAdminPin").value = savedAdminPin;
    }
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

function syncAdminPin(sourceId) {
  const src = document.getElementById(sourceId);
  if (!src) return;
  const val = src.value;
  const otherId = sourceId === "adminPin" ? "fleetAdminPin" : "adminPin";
  const other = document.getElementById(otherId);
  if (other && other.value !== val) {
    other.value = val;
  }
  if (val.trim()) {
    localStorage.setItem("etap_admin_pin", val.trim());
  }
}

function getAdminPinValue(preferredInputId = "adminPin") {
  const preferred = document.getElementById(preferredInputId);
  const fallbackId = preferredInputId === "adminPin" ? "fleetAdminPin" : "adminPin";
  const fallback = document.getElementById(fallbackId);
  const val = (preferred && preferred.value.trim()) || (fallback && fallback.value.trim()) || "";
  if (val) {
    localStorage.setItem("etap_admin_pin", val);
  }
  return val;
}

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
    const isFleetActive = document.getElementById("adminSubFleetView")?.classList.contains("active");
    if (isFleetActive) {
      fetchAdminFleet();
    } else {
      fetchOnlineBoards();
    }
    fetchSchoolName();
  }

  // Kamera açıksa ve başka sekmeye geçildiyse kapat
  if (tabName !== "teacher" && isScanning) {
    stopCameraScanner();
  }
}

function switchAdminSubTab(subTabName) {
  const fleetBtn = document.getElementById("adminSubFleetBtn");
  const manageBtn = document.getElementById("adminSubManageBtn");
  const fleetView = document.getElementById("adminSubFleetView");
  const manageView = document.getElementById("adminSubManageView");

  if (!fleetBtn || !manageBtn || !fleetView || !manageView) return;

  fleetBtn.classList.remove("active");
  manageBtn.classList.remove("active");
  fleetView.classList.remove("active");
  manageView.classList.remove("active");

  if (subTabName === "fleet") {
    fleetBtn.classList.add("active");
    fleetView.classList.add("active");
    fetchAdminFleet();
  } else if (subTabName === "manage") {
    manageBtn.classList.add("active");
    manageView.classList.add("active");
    fetchOnlineBoards();
    fetchSchoolName();
  }
}

// -------------------------------------------------------------
// 📡 Çevrimiçi Tahtaları Listeleme (Sadece Aktif Tahtalar)
// -------------------------------------------------------------
async function fetchOnlineBoards() {
  const adminTarget = document.getElementById("adminTarget");

  try {
    const res = await fetch("/api/boards?online_only=true");
    const data = await res.json();

    if (data.success && data.boards) {
      if (adminTarget) {
        adminTarget.innerHTML = '<option value="all">📢 TÜM OKUL (Tüm Tahtalar)</option>';
      }

      // Sadece ve sadece çevrimiçi (online) tahtaları göster
      const onlineBoards = data.boards.filter(b => b.online);
      cachedOnlineBoards = onlineBoards;

      if (adminTarget) {
        onlineBoards.forEach(b => {
          const displayName = b.name || b.id;
          // Müdür paneli için hedef
          const adminOpt = document.createElement("option");
          adminOpt.value = b.id;
          adminOpt.textContent = `🖥️ ${displayName}`;
          adminTarget.appendChild(adminOpt);
        });
      }

      // 1A Öğretmen dokunmatik sınıf kartlarını & 2A bilgi rozetini güncelle
      renderTeacherBoardGrid(onlineBoards);

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

function selectTeacherBoard(boardId, boardName, boardStatus = "") {
  const cleanId = (boardId || "").trim();
  if (!cleanId) return;

  const cleanName = (boardName || cleanId).trim();
  selectedBoard = {
    id: cleanId,
    name: cleanName,
    status: boardStatus || ""
  };

  localStorage.setItem("etap_selected_board", cleanId);
  localStorage.setItem("etap_selected_board_name", cleanName);

  updateSelectedBoardBadge();

  document.querySelectorAll("#teacherBoardGrid .board-chip").forEach(chip => {
    chip.classList.toggle("selected", chip.dataset.boardId === cleanId);
  });
}

// Seçili Tahta ID'sini Al
function getSelectedBoardId() {
  return (selectedBoard.id || "").trim();
}

function getSelectedBoardDisplayName() {
  return (selectedBoard.name || selectedBoard.id || "").trim();
}

function updateSelectedBoardBadge() {
  const badge = document.getElementById("selectedBoardBadge");
  const titleEl = document.getElementById("selectedBoardTitle");
  const statusEl = document.getElementById("selectedBoardStatus");
  const metaEl = document.getElementById("selectedBoardMeta");
  if (!badge || !titleEl || !statusEl || !metaEl) return;

  if (!selectedBoard.id) {
    badge.classList.add("empty");
    titleEl.textContent = "👆 Yukarıdan bir sınıf seçin veya QR okutun";
    statusEl.className = "selected-status-pill hidden";
    statusEl.textContent = "";
    metaEl.classList.add("hidden");
    metaEl.textContent = "";
    return;
  }

  badge.classList.remove("empty");
  titleEl.textContent = `🖥️ Seçili: ${getSelectedBoardDisplayName()}`;

  const statusMap = {
    unlocked: { text: "🟢 Açık", cls: "unlocked" },
    locked: { text: "🔒 Kilitli", cls: "locked" },
    updating: { text: "🔄 Güncelleniyor", cls: "updating" },
    offline: { text: "⚪ Çevrimdışı", cls: "offline" }
  };
  const info = statusMap[selectedBoard.status];
  if (info) {
    statusEl.textContent = info.text;
    statusEl.className = `selected-status-pill ${info.cls}`;
  } else {
    statusEl.className = "selected-status-pill hidden";
    statusEl.textContent = "";
  }

  metaEl.textContent = `Kimlik: ${selectedBoard.id}`;
  metaEl.classList.remove("hidden");
}

function renderTeacherBoardGrid(boards) {
  const grid = document.getElementById("teacherBoardGrid");
  const countEl = document.getElementById("onlineBoardCount");
  const searchInput = document.getElementById("boardSearchInput");
  if (!grid) return;

  const list = Array.isArray(boards) ? boards : [];
  if (countEl) {
    countEl.textContent = String(list.length);
  }

  if (searchInput) {
    if (list.length > 6) {
      searchInput.classList.remove("hidden");
    } else {
      searchInput.classList.add("hidden");
      searchInput.value = "";
    }
  }

  // Seçili tahta canlı listedeyse adını/durumunu tazele; tek tahta varsa otomatik seç
  if (selectedBoard.id) {
    const liveMatch = list.find(
      b => b.id === selectedBoard.id || (b.name && b.name === selectedBoard.id)
    );
    if (liveMatch) {
      selectedBoard.id = liveMatch.id;
      selectedBoard.name = liveMatch.name || liveMatch.id;
      selectedBoard.status = liveMatch.status || "locked";
      localStorage.setItem("etap_selected_board", selectedBoard.id);
      localStorage.setItem("etap_selected_board_name", selectedBoard.name);
    } else {
      selectedBoard.status = "offline";
    }
  } else if (list.length === 1) {
    const only = list[0];
    selectedBoard = {
      id: only.id,
      name: only.name || only.id,
      status: only.status || "locked"
    };
    localStorage.setItem("etap_selected_board", selectedBoard.id);
    localStorage.setItem("etap_selected_board_name", selectedBoard.name);
  }
  updateSelectedBoardBadge();

  if (list.length === 0) {
    grid.innerHTML = '<div class="board-grid-empty">⚠️ Şu an çevrimiçi tahta bulunmuyor</div>';
    return;
  }

  const query = (searchInput && !searchInput.classList.contains("hidden") ? searchInput.value : "").trim().toLocaleLowerCase("tr-TR");
  const filtered = query
    ? list.filter(b => {
        const name = (b.name || "").toLocaleLowerCase("tr-TR");
        const id = (b.id || "").toLocaleLowerCase("tr-TR");
        return name.includes(query) || id.includes(query);
      })
    : list;

  if (filtered.length === 0) {
    grid.innerHTML = '<div class="board-grid-empty">🔍 Aramanızla eşleşen sınıf bulunamadı</div>';
    return;
  }

  grid.innerHTML = "";
  filtered.forEach(b => {
    const displayName = b.name || b.id;
    const status = b.status || "locked";
    const statusEmoji = status === "unlocked" ? "🟢" : (status === "updating" ? "🔄" : "🔒");

    const chip = document.createElement("button");
    chip.type = "button";
    chip.dataset.boardId = b.id;
    chip.className = `board-chip status-${status}${selectedBoard.id === b.id ? " selected" : ""}`;

    const iconSpan = document.createElement("span");
    iconSpan.className = "board-chip-icon";
    iconSpan.textContent = statusEmoji;

    const nameSpan = document.createElement("span");
    nameSpan.className = "board-chip-name";
    nameSpan.textContent = displayName;

    chip.appendChild(iconSpan);
    chip.appendChild(nameSpan);
    chip.addEventListener("click", () => {
      selectTeacherBoard(b.id, displayName, status);
    });
    grid.appendChild(chip);
  });
}

function filterTeacherBoards() {
  renderTeacherBoardGrid(cachedOnlineBoards);
}

function updateTeacherPinUI(showEditor) {
  const compactRow = document.getElementById("teacherPinCompactRow");
  const editor = document.getElementById("teacherPinEditor");
  const pinInput = document.getElementById("teacherPin");
  if (!compactRow || !editor || !pinInput) return;

  const hasPin = pinInput.value.trim().length > 0;
  if (showEditor || !hasPin) {
    compactRow.classList.add("hidden");
    editor.classList.remove("hidden");
  } else {
    editor.classList.add("hidden");
    compactRow.classList.remove("hidden");
  }
}

function toggleTeacherPinEditor(showEditor) {
  updateTeacherPinUI(showEditor);
  if (showEditor) {
    const pinInput = document.getElementById("teacherPin");
    if (pinInput) {
      pinInput.focus();
      pinInput.select();
    }
  }
}

function saveAndCollapseTeacherPin() {
  const pinInput = document.getElementById("teacherPin");
  const val = (pinInput?.value || "").trim();
  if (!val) {
    showToast("Lütfen geçerli bir Öğretmen PIN kodu girin!", "error");
    if (pinInput) pinInput.focus();
    return;
  }
  localStorage.setItem("etap_teacher_pin", val);
  updateTeacherPinUI(false);
  showToast("Öğretmen PIN kodu kaydedildi.", "success");
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
        selectTeacherBoard(boardId, boardName, "");
      }
    } else {
      selectTeacherBoard(decodedText, decodedText, "");
    }
  } catch (e) {
    selectTeacherBoard(decodedText, decodedText, "");
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
    toggleTeacherPinEditor(true);
    showToast("Lütfen Ortak Öğretmen PIN Kodunu girin!", "error");
    return;
  }

  localStorage.setItem("etap_teacher_pin", pin);
  localStorage.setItem("etap_selected_board", boardId);
  localStorage.setItem("etap_selected_board_name", getSelectedBoardDisplayName());

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
      updateTeacherPinUI(false);
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

  if (!boardId) {
    showToast("Lütfen bir sınıf/tahta seçin!", "error");
    return;
  }
  if (!pin) {
    toggleTeacherPinEditor(true);
    showToast("Lütfen Ortak Öğretmen PIN Kodunu girin!", "error");
    return;
  }

  localStorage.setItem("etap_teacher_pin", pin);

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
    btn.textContent = "🔒 Kilitle";
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
    toggleTeacherPinEditor(true);
    showToast("Lütfen yetkili PIN kodunuzu girin!", "error");
    return;
  }

  const modal = document.getElementById("powerModal");
  const modalDesc = document.getElementById("modalDesc");
  const displayName = getSelectedBoardDisplayName();

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
// 📢 Müdür / İdare Duyuru Yayını & Bağlantı Gönderme
// -------------------------------------------------------------
async function sendBroadcast() {
  const adminPin = document.getElementById("adminPin").value.trim();
  const target = document.getElementById("adminTarget").value;
  const message = document.getElementById("adminMessage").value.trim();
  const linkUrl = (document.getElementById("adminLinkUrl")?.value || "").trim();
  const linkLabel = (document.getElementById("adminLinkLabel")?.value || "").trim();
  const duration = parseInt(document.getElementById("adminDuration").value) || 120;

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
        link_url: linkUrl,
        link_label: linkLabel,
        duration_sec: duration
      })
    });
    const data = await res.json();

    if (res.ok && data.success) {
      showToast(data.message, "success");
      document.getElementById("adminMessage").value = "";
      if (document.getElementById("adminLinkUrl")) {
        document.getElementById("adminLinkUrl").value = "";
      }
      if (document.getElementById("adminLinkLabel")) {
        document.getElementById("adminLinkLabel").value = "";
      }
    } else {
      showToast(data.detail || "Duyuru iletilemedi!", "error");
    }
  } catch (err) {
    showToast("Sunucu hatası: " + err, "error");
  }
}

async function clearBroadcast() {
  const adminPin = document.getElementById("adminPin").value.trim();
  const target = document.getElementById("adminTarget").value;

  if (!adminPin) {
    showToast("Lütfen İdare PIN kodunu girin!", "error");
    return;
  }

  try {
    const res = await fetch("/api/broadcast/clear", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        admin_pin: adminPin,
        target: target
      })
    });
    const data = await res.json();

    if (res.ok && data.success) {
      showToast(data.message || "Aktif duyurular temizlendi!", "success");
    } else {
      showToast(data.detail || "Duyurular temizlenemedi!", "error");
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
    const isUpdating = b.status === "updating";
    let statusText = isUnlocked ? "🟢 Açık (Derste)" : "🔒 Kilitli (Beklemede)";
    let statusClass = isUnlocked ? "online-unlocked" : "online-locked";
    if (isUpdating) {
      statusText = b.update_msg ? `🔄 ${escapeHtml(b.update_msg)}` : "🔄 Güncelleniyor...";
      statusClass = "online-updating";
    }
    const displayName = b.name || b.id;
    const versionBadge = b.version
      ? `<span class="fleet-version-badge">${escapeHtml(b.version)}</span>`
      : "";

    const card = document.createElement("div");
    card.className = "fleet-card";
    card.innerHTML = `
      <div class="fleet-info">
        <div class="fleet-top-row">
          <span class="fleet-name">🖥️ ${escapeHtml(displayName)}</span>
          ${versionBadge}
        </div>
        <span class="fleet-status ${statusClass}">${statusText}</span>
      </div>
      <div class="fleet-actions">
        <button type="button" class="btn-update-board" onclick="triggerSingleBoardUpdate('${escapeHtml(b.id)}', '${escapeHtml(displayName)}')" title="Bu tahtayı uzaktan güncelle">
          🔄 Güncelle
        </button>
        <button type="button" class="btn-screenshot" onclick="openScreenshotModal('${escapeHtml(b.id)}', '${escapeHtml(displayName)}')">
          📸 Ekranı Gör
        </button>
      </div>
    `;
    container.appendChild(card);
  });
}

async function openScreenshotModal(boardId, boardName) {
  const adminPin = getAdminPinValue("adminPin");
  if (!adminPin) {
    showToast("Lütfen yukarıdaki İdare Giriş Kodunu giriniz!", "error");
    const pinEl = document.getElementById("adminPin");
    if (pinEl) pinEl.focus();
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
  const adminPin = getAdminPinValue("fleetAdminPin");
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
    poweroff: "/api/bulk/poweroff",
    update: "/api/bulk/update"
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

function confirmBulkUpdate() {
  const adminPin = document.getElementById("adminPin").value.trim();
  if (!adminPin) {
    showToast("Lütfen önce yukarıdaki İdare Giriş Kodunu giriniz!", "error");
    document.getElementById("adminPin").focus();
    return;
  }

  if (confirm("🔄 DİKKAT: Okuldaki çevrimiçi TÜM akıllı tahtalar GitHub'dan en güncel sürüme otomatik güncellenip yeniden başlatılacaktır.\n\nDevam etmek istiyor musunuz?")) {
    triggerBulkAction("update");
  }
}

async function triggerSingleBoardUpdate(boardId, boardName) {
  const adminPin = getAdminPinValue("adminPin");
  if (!adminPin) {
    showToast("Lütfen önce yukarıdaki İdare Giriş Kodunu giriniz!", "error");
    const pinEl = document.getElementById("adminPin");
    if (pinEl) pinEl.focus();
    return;
  }

  if (!confirm(`🔄 '${boardName}' tahtası GitHub üzerinden en güncel sürüme güncellenip yeniden başlatılsın mı?`)) {
    return;
  }

  try {
    const res = await fetch("/api/board/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ board_id: boardId, admin_pin: adminPin })
    });
    const data = await res.json();

    if (res.ok && data.success) {
      showToast(data.message, "success");
      fetchOnlineBoards();
    } else {
      showToast(data.detail || "Güncelleme komutu gönderilemedi!", "error");
    }
  } catch (err) {
    showToast("Sunucu hatası: " + err, "error");
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
