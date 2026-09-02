// ═══════════════════════════════════════════════════════════════
// Smart Study Space — Dashboard Controller (Real-Time)
// ═══════════════════════════════════════════════════════════════

import { database, ref, onValue } from "./firebase-config.js";
import {
  updateAnalyticsPanel,
  getOccupancyRate,
  updateGenderAnalyticsPanel
} from "./analytics.js";

// ── State ─────────────────────────────────────────────────────
const previousStatuses = {};          // Track status for pulse animation
let activeDurationTimers = {};        // Per-seat interval IDs
let latestSeatsData = null;           // Cache for analytics
let latestSummaryData = null;

// ── Audio Alarm Setup ─────────────────────────────────────────
const alarmAudio = new Audio("table.mp3");
alarmAudio.loop = false;              // Play single cycles to control repetitions
let audioAllowed = false;             // Track browser autoplay permission
let isAlarmPlaying = false;           // State flag to prevent interruption
let latestSoundStatus = "quiet";      // Cache the latest sound state from Firebase

// Audio loading error diagnostic
alarmAudio.addEventListener("error", (e) => {
  console.error("[Audio] Error loading table.mp3. Check file location and permissions:", e);
});

// Play alarm warning helper
function playAlarm() {
  if (isAlarmPlaying) return;
  isAlarmPlaying = true;
  alarmAudio.currentTime = 0;
  
  console.log("[Audio] Attempting playback...");
  alarmAudio.play()
    .then(() => {
      console.log("[Audio] Playback succeeded.");
      audioAllowed = true;
      updateAudioStatusText();
    })
    .catch(err => {
      console.warn("[Audio] Playback blocked by browser autoplay policy:", err.message);
      isAlarmPlaying = false;
      audioAllowed = false;
      updateAudioStatusText();
    });
}

// Track when audio completes its cycle
alarmAudio.addEventListener("ended", () => {
  isAlarmPlaying = false;
  console.log("[Audio] Playback cycle finished. Current state check:", latestSoundStatus);
  
  // Replay if sound status is still noisy after current playback completes
  if (latestSoundStatus === "noisy" || latestSoundStatus === "loud") {
    playAlarm();
  }
});

// Unlock audio context on user interaction
const unlockAudio = () => {
  if (audioAllowed) return;
  console.log("[Audio] User interaction detected. Attempting to unlock audio context...");
  alarmAudio.play()
    .then(() => {
      alarmAudio.pause();
      alarmAudio.currentTime = 0;
      audioAllowed = true;
      console.log("[Audio] Audio context successfully unlocked!");
      updateAudioStatusText();
      
      // If it was already noisy before clicking, play the alarm now!
      if (latestSoundStatus === "noisy" || latestSoundStatus === "loud") {
        playAlarm();
      }
      removeUnlockListeners();
    })
    .catch(err => {
      console.warn("[Audio] Unlock attempt failed (still blocked):", err);
    });
};

function removeUnlockListeners() {
  document.removeEventListener("click", unlockAudio);
  document.removeEventListener("keydown", unlockAudio);
  document.removeEventListener("touchstart", unlockAudio);
}

document.addEventListener("click", unlockAudio);
document.addEventListener("keydown", unlockAudio);
document.addEventListener("touchstart", unlockAudio);

// Helper to keep the UI sound status text up to date
function updateAudioStatusText() {
  const statusEl = document.getElementById("soundStatus");
  if (!statusEl) return;
  
  if (latestSoundStatus === "noisy" || latestSoundStatus === "loud") {
    statusEl.textContent = audioAllowed ? "🔊 Noisy" : "🔊 Noisy (Click anywhere to enable alarm sound)";
    statusEl.style.color = "var(--occupied)";
  } else {
    statusEl.textContent = audioAllowed ? "🔇 Quiet" : "🔇 Quiet (Click anywhere to enable alarm sound)";
    statusEl.style.color = "var(--available)";
  }
}

// ── Clock ─────────────────────────────────────────────────────
function startClock() {
  const clockEl = document.getElementById("headerClock");
  const dateEl  = document.getElementById("headerDate");

  if (!clockEl && !dateEl) return;

  function tick() {
    const now = new Date();
    if (clockEl) {
      clockEl.textContent = now.toLocaleTimeString("en-US", {
        hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: true
      });
    }
    if (dateEl) {
      dateEl.textContent = now.toLocaleDateString("en-US", {
        weekday: "short", month: "short", day: "numeric", year: "numeric"
      });
    }
  }
  tick();
  setInterval(tick, 1000);
}

// ── Utility: Format Duration ──────────────────────────────────
/**
 * Converts total seconds to a human-readable "Xh Ym Zs" string.
 * @param {number} seconds
 * @returns {string}
 */
function formatDuration(seconds) {
  if (seconds == null || isNaN(seconds) || seconds <= 0) return "—";
  const s = Math.floor(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const parts = [];
  if (h > 0) parts.push(`${h}h`);
  if (m > 0) parts.push(`${m}m`);
  parts.push(`${sec}s`);
  return parts.join(" ");
}

// ── Utility: Status → CSS class ───────────────────────────────
/**
 * Returns a normalised status string used as data-status attribute.
 */
function getStatusClass(status) {
  if (!status) return "Unknown";
  const s = status.toString().toLowerCase();
  if (s === "available" || s === "free")        return "Available";
  if (s === "occupied")                          return "Occupied";
  if (s.includes("bag"))                         return "Bag Detected";
  return "Unknown";
}

// ── Utility: Status → Color token ─────────────────────────────
function statusColor(status) {
  switch (status) {
    case "Available":    return "var(--available)";
    case "Occupied":     return "var(--occupied)";
    case "Bag Detected": return "var(--bag)";
    default:             return "var(--unknown)";
  }
}

// ── Animate: Pulse on Status Change ───────────────────────────
function animateStatusChange(element) {
  element.classList.remove("is-pulsing");
  // Force reflow so the animation restarts
  void element.offsetWidth;
  element.classList.add("is-pulsing");
  element.addEventListener("animationend", () => {
    element.classList.remove("is-pulsing");
  }, { once: true });
}

// ── Update a Single Seat Card ─────────────────────────────────
/**
 * @param {number} seatId  — 1 through 4
 * @param {object} data    — Seat data from Firebase
 */
function updateSeatCard(seatId, data) {
  const card     = document.getElementById(`seat-${seatId}`);
  const badge    = document.getElementById(`badge-${seatId}`);
  const fsr      = document.getElementById(`fsr-${seatId}`);
  const human    = document.getElementById(`human-${seatId}`);
  const duration = document.getElementById(`duration-${seatId}`);
  const lastUpd  = document.getElementById(`lastUpdate-${seatId}`);
  const genderEl = document.getElementById(`gender-${seatId}`);

  if (!card || !data) return;

  const status = getStatusClass(data.status);

  // Pulse animation if status changed
  if (previousStatuses[seatId] && previousStatuses[seatId] !== status) {
    animateStatusChange(card);
  }
  previousStatuses[seatId] = status;

  // Update data-status attribute (drives all CSS status styles)
  card.setAttribute("data-status", status);

  // Badge
  badge.textContent = status;

  // FSR
  fsr.textContent = data.fsrValue != null ? data.fsrValue : "—";

  // Human detected
  if (data.humanDetected != null) {
    const detected = data.humanDetected === true ||
                     data.humanDetected === 1 ||
                     data.humanDetected === "true" ||
                     data.humanDetected === "Yes";
    human.textContent = detected ? "✅ Yes" : "❌ No";
    human.style.color = detected ? "var(--available)" : "var(--text-secondary)";
  } else {
    human.textContent = "—";
    human.style.color = "";
  }

  // ── Gender Detection (from Raspberry Pi) ───────────────────
  if (genderEl) {
    const lastEvent  = (data.genderLastEvent || "").toString().trim().toUpperCase();
    const gender     = lastEvent === "EXIT" ? "Unknown" : (data.gender || "");
    const confidence = lastEvent === "EXIT" ? 0 : (data.genderConfidence != null ? data.genderConfidence : 0);

    // Reset classes
    genderEl.classList.remove("is-male", "is-female", "is-unknown");

    if (gender === "Male") {
      genderEl.textContent = `♂ Male (${confidence.toFixed(1)}%)`;
      genderEl.classList.add("is-male");
    } else if (gender === "Female") {
      genderEl.textContent = `♀ Female (${confidence.toFixed(1)}%)`;
      genderEl.classList.add("is-female");
    } else {
      genderEl.textContent = "—";
      genderEl.classList.add("is-unknown");
    }
  }

  // Duration — live counter
  setupDurationTimer(seatId, data);

  // Last update
  if (data.lastUpdate) {
    const ts = typeof data.lastUpdate === "number"
      ? new Date(data.lastUpdate * 1000)
      : new Date(data.lastUpdate);
    if (!isNaN(ts.getTime())) {
      lastUpd.textContent = `Last update: ${ts.toLocaleTimeString("en-US", {
        hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: true
      })}`;
    } else {
      lastUpd.textContent = `Last update: ${data.lastUpdate}`;
    }
  } else {
    lastUpd.textContent = "Last update: —";
  }
}

// ── Update a Single Monitor Seat Card (Styled like Screenshot) ──
/**
 * @param {number} seatId  — 1 through 4
 * @param {object} data    — Seat data from Firebase
 */
function updateMonitorSeatCard(seatId, data) {
  const card       = document.getElementById(`monitor-seat-${seatId}`);
  const badge      = document.getElementById(`monitor-badge-${seatId}`);
  const circle     = document.getElementById(`monitor-circle-${seatId}`);
  const statusText = document.getElementById(`monitor-status-${seatId}`);

  if (!card || !data) return;

  const status = getStatusClass(data.status); // "Available", "Occupied", "Bag Detected"
  const lastEvent = (data.genderLastEvent || "").toString().trim().toUpperCase();
  const gender = lastEvent === "EXIT" ? "Unknown" : (data.gender || "Unknown");

  // 1. Set status attribute (drives circle borders and styles)
  card.setAttribute("data-status", status.toLowerCase().replace(" ", "-"));

  // 2. Set gender badge text and style class
  badge.textContent = gender.toUpperCase();
  badge.className = `monitor-seat-badge monitor-seat-badge--${gender.toLowerCase()}`;

  // 3. Set status text
  let displayStatus = "Available";
  if (status === "Occupied") displayStatus = "Occupied";
  if (status === "Bag Detected") displayStatus = "Bag";
  
  statusText.textContent = `Status - ${displayStatus}`;
  statusText.className = `monitor-seat-status monitor-seat-status--${displayStatus.toLowerCase()}`;

  // 4. Set Circle SVG Icon
  let iconHtml = "";
  if (status === "Bag Detected") {
    // Bag icon
    iconHtml = `
      <svg class="monitor-icon" viewBox="0 0 24 24" fill="currentColor">
        <path d="M17 6h-2V5c0-1.66-1.34-3-3-3S9 3.34 9 5v1H7c-1.1 0-2 .9-2 2v11c0 1.1.9 2 2 2h10c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm-5-2c.55 0 1 .45 1 1v1h-2V5c0-.55.45-1 1-1zm5 15H7V8h10v11z"/>
      </svg>
    `;
  } else {
    // Human icon based on gender
    if (gender === "Female") {
      iconHtml = `
        <svg class="monitor-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2c1.1 0 2 .9 2 2s-.9 2-2 2-2-.9-2-2 .9-2 2-2zm2.4 7h-4.8c-.8 0-1.4.6-1.5 1.3l-1.1 6c-.1.6.4 1.2 1 1.2h1.7v4.5c0 .8.7 1.5 1.5 1.5s1.5-.7 1.5-1.5v-4.5h1.7c.6 0 1.1-.6 1-1.2l-1.1-6c-.1-.7-.7-1.3-1.4-1.3z"/>
        </svg>
      `;
    } else {
      // Default/Male
      iconHtml = `
        <svg class="monitor-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2c1.1 0 2 .9 2 2s-.9 2-2 2-2-.9-2-2 .9-2 2-2zm2 7H10c-.55 0-1 .45-1 1v6h2v6h2v-6h2v-6c0-.55-.45-1-1-1z"/>
        </svg>
      `;
    }
  }
  circle.innerHTML = iconHtml;
}

// ── Live Duration Timer ───────────────────────────────────────
function setupDurationTimer(seatId, data) {
  const el = document.getElementById(`duration-${seatId}`);

  // Clear any existing timer
  if (activeDurationTimers[seatId]) {
    clearInterval(activeDurationTimers[seatId]);
    activeDurationTimers[seatId] = null;
  }

  const status = getStatusClass(data.status);

  // If occupied and we have a startTime, run a live counter
  if (status === "Occupied" && data.startTime) {
    const startMs = typeof data.startTime === "number"
      ? (data.startTime < 1e12 ? data.startTime * 1000 : data.startTime)
      : new Date(data.startTime).getTime();

    if (!isNaN(startMs)) {
      function tick() {
        const elapsed = Math.max(0, Math.floor((Date.now() - startMs) / 1000));
        el.textContent = formatDuration(elapsed);
        el.style.color = "var(--available)";
      }
      tick();
      activeDurationTimers[seatId] = setInterval(tick, 1000);
      return;
    }
  }

  // Fallback: use currentUsage if provided
  if (data.currentUsage != null && data.currentUsage > 0) {
    el.textContent = formatDuration(data.currentUsage);
    el.style.color = "var(--text-primary)";
  } else {
    el.textContent = "—";
    el.style.color = "var(--text-muted)";
  }
}

// ── Update Summary Section ────────────────────────────────────
function updateSummary(data) {
  if (!data) return;

  const available = data.availableSeats  ?? 0;
  const occupied  = data.occupiedSeats   ?? 0;
  const bag       = data.bagDetectedSeats ?? 0;
  const total     = data.totalSeats       ?? 4;

  animateCounter("availableCount", available);
  animateCounter("occupiedCount",  occupied);
  animateCounter("bagCount",       bag);
  animateCounter("totalCount",     total);

  // Update Monitor Row (Screenshot View)
  const monitorTotal = document.getElementById("monitorTotalSeats");
  const monitorOcc   = document.getElementById("monitorOccupied");
  const monitorAvail = document.getElementById("monitorAvailable");

  if (monitorTotal) monitorTotal.textContent = total;
  if (monitorOcc)   monitorOcc.textContent   = occupied + bag;
  if (monitorAvail) monitorAvail.textContent = available;

  // Donut chart
  updateDonut(occupied, bag, available, total);
}

// ── Animated Counter ──────────────────────────────────────────
function animateCounter(elementId, targetValue) {
  const el = document.getElementById(elementId);
  if (!el) return;
  const current = parseInt(el.textContent) || 0;
  if (current === targetValue) return;

  const diff  = targetValue - current;
  const steps = Math.min(Math.abs(diff), 10);
  const step  = diff / steps;
  let i = 0;

  const interval = setInterval(() => {
    i++;
    if (i >= steps) {
      el.textContent = targetValue;
      clearInterval(interval);
    } else {
      el.textContent = Math.round(current + step * i);
    }
  }, 40);
}

// ── Donut Chart Update ────────────────────────────────────────
function updateDonut(occupied, bag, available, total) {
  const ring    = document.getElementById("donutRing");
  const percent = document.getElementById("donutPercent");
  if (!ring) return;

  const t = total || 4;
  const occPct  = (occupied / t) * 100;
  const bagPct  = (bag / t) * 100;
  const freePct = (available / t) * 100;

  const p1 = occPct;
  const p2 = occPct + bagPct;

  ring.style.background = `conic-gradient(
    var(--occupied)  0% ${p1}%,
    var(--bag)       ${p1}% ${p2}%,
    var(--available) ${p2}% 100%
  )`;

  const overallOcc = Math.round(((occupied + bag) / t) * 100);
  percent.textContent = `${overallOcc}%`;
}

// ── Update Sound Indicator ────────────────────────────────────
function updateSound(data) {
  if (!data) return;

  const indicator  = document.getElementById("soundIndicator");
  const statusEl   = document.getElementById("soundStatus");
  const levelEl    = document.getElementById("soundLevel");

  if (!indicator) return;

  const soundStatus = (data.status || "").toString().toLowerCase();
  const soundLevel  = data.level != null ? data.level : "—";

  console.log("[Audio Debug] updateSound called. Status:", soundStatus, "Level:", soundLevel, "audioAllowed:", audioAllowed, "isAlarmPlaying:", isAlarmPlaying);

  // Cache the latest status globally so the 'ended' listener can check it
  latestSoundStatus = soundStatus;

  // Remove previous state classes
  indicator.classList.remove("is-noisy", "is-quiet");

  if (soundStatus === "noisy" || soundStatus === "loud") {
    indicator.classList.add("is-noisy");
    updateAudioStatusText();

    // Start playback if not already playing
    if (!isAlarmPlaying) {
      playAlarm();
    }
  } else {
    indicator.classList.add("is-quiet");
    updateAudioStatusText();

    // DO NOT pause here! Let the audio finish playing its full cycle.
    // The 'ended' event listener will stop/restart it once complete.
  }

  levelEl.textContent = `Level: ${soundLevel}`;
}

// ── Gender Event Log ──────────────────────────────────────────
function updateGenderEventLog(data) {
  const logEl = document.getElementById("genderEventLog");
  if (!logEl) return;

  if (!data || typeof data !== "object") {
    logEl.innerHTML = '<p class="event-log__empty">Waiting for gender detection events…</p>';
    return;
  }

  // Convert Firebase push-key map to sorted array (newest first)
  const entries = Object.entries(data)
    .map(([key, val]) => ({ key, ...val }))
    .sort((a, b) => {
      // Sort by timestamp descending (newest first)
      if (a.timestamp && b.timestamp) {
        return b.timestamp.localeCompare(a.timestamp);
      }
      return b.key.localeCompare(a.key);
    })
    .slice(0, 20); // Show latest 20

  if (entries.length === 0) {
    logEl.innerHTML = '<p class="event-log__empty">Waiting for gender detection events…</p>';
    return;
  }

  logEl.innerHTML = entries.map((entry, idx) => {
    const eventLower = (entry.event || "").toLowerCase().replace("_", "-");
    const genderClass = entry.gender === "Male" ? "male" : entry.gender === "Female" ? "female" : "";
    const confStr = entry.confidence > 0 ? `${entry.confidence}%` : "N/A";

    // Format timestamp — show only time portion
    let timeStr = "";
    if (entry.timestamp) {
      const ts = new Date(entry.timestamp);
      if (!isNaN(ts.getTime())) {
        timeStr = ts.toLocaleTimeString("en-US", {
          hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: true
        });
      } else {
        timeStr = entry.timestamp;
      }
    }

    return `
      <div class="event-log__entry event-log__entry--${eventLower}" style="animation-delay: ${idx * 0.04}s">
        <span class="event-log__time">${timeStr}</span>
        <span class="event-log__badge event-log__badge--${eventLower}">${entry.event || "?"}</span>
        <span>Seat ${entry.seat || "?"}</span>
        <span class="event-log__gender--${genderClass}">${entry.gender || "?"} (${confStr})</span>
      </div>
    `;
  }).join("");
}

// ── Connection State Monitor ──────────────────────────────────
function monitorConnection() {
  const connRef = ref(database, ".info/connected");
  onValue(connRef, (snap) => {
    const dot  = document.getElementById("connectionDot");
    const text = document.getElementById("connectionText");

    if (snap.val() === true) {
      dot.className  = "connection-dot connection-dot--online";
      text.textContent = "Connected";
    } else {
      dot.className  = "connection-dot connection-dot--offline";
      text.textContent = "Disconnected";
    }
  });
}

// ── Firebase Real-Time Listeners ──────────────────────────────
function initListeners() {
  // 1. Seats
  const seatsRef = ref(database, "SmartStudySpace/Seats");
  onValue(seatsRef, (snapshot) => {
    const data = snapshot.val();
    if (!data) return;

    latestSeatsData = data;

    // Update each seat card (Seat1 → 1, Seat2 → 2, etc.)
    for (let i = 1; i <= 4; i++) {
      const key = `Seat${i}`;
      if (data[key]) {
        updateSeatCard(i, data[key]);
        updateMonitorSeatCard(i, data[key]);
      }
    }

    // Update analytics
    if (latestSummaryData) {
      updateAnalyticsPanel(latestSeatsData, latestSummaryData);
    }

    // Update gender analytics
    updateGenderAnalyticsPanel(latestSeatsData);
  });

  // 2. Summary
  const summaryRef = ref(database, "SmartStudySpace/Summary");
  onValue(summaryRef, (snapshot) => {
    const data = snapshot.val();
    if (!data) return;

    latestSummaryData = data;
    updateSummary(data);

    // Update analytics
    if (latestSeatsData) {
      updateAnalyticsPanel(latestSeatsData, latestSummaryData);
    }
  });

  // 3. Sound
  const soundRef = ref(database, "SmartStudySpace/Sound");
  onValue(soundRef, (snapshot) => {
    const data = snapshot.val();
    if (data) updateSound(data);
  });

  // 4. Gender Event Log (live ticker)
  const genderLogRef = ref(database, "SmartStudySpace/GenderEventLog");
  onValue(genderLogRef, (snapshot) => {
    const data = snapshot.val();
    updateGenderEventLog(data);
  });
}

// ── Bootstrap ─────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  startClock();
  monitorConnection();
  initListeners();

  // Collapsible Admin Panel Toggle
  const adminToggleBtn = document.getElementById("adminToggleBtn");
  const adminPanel = document.getElementById("adminPanel");
  
  if (adminToggleBtn && adminPanel) {
    adminToggleBtn.addEventListener("click", () => {
      const isExpanded = adminPanel.classList.toggle("expanded");
      adminToggleBtn.classList.toggle("active", isExpanded);
      console.log(`[Admin] Panel visibility changed. Expanded: ${isExpanded}`);
    });
  }
});
