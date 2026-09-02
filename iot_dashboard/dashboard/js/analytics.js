// ═══════════════════════════════════════════════════════════════
// Smart Study Space — Analytics Module
// ═══════════════════════════════════════════════════════════════

// ── Constants ─────────────────────────────────────────────────
// Total possible seconds in a "day" for utilisation calculations.
// Default: 16 hours (a reasonable study-space operating window).
const TOTAL_POSSIBLE_SECONDS = 16 * 60 * 60; // 57 600 s

// ── Helpers ───────────────────────────────────────────────────

/**
 * Safely extract numeric value, defaulting to 0.
 */
function num(value) {
  const n = Number(value);
  return isNaN(n) ? 0 : n;
}

/**
 * Format seconds into human-readable string.
 */
function fmtDuration(seconds) {
  if (seconds <= 0) return "0m";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

// ── Core Analytics Functions ──────────────────────────────────

/**
 * Returns the seat key (e.g. "Seat 2") with the highest totalUsageToday.
 */
export function getMostUsedSeat(seatsData) {
  let maxKey = null;
  let maxVal = -1;

  for (const [key, seat] of Object.entries(seatsData)) {
    const usage = num(seat.totalUsageToday);
    if (usage > maxVal) {
      maxVal = usage;
      maxKey = key;
    }
  }

  if (maxKey && maxVal > 0) {
    return formatSeatName(maxKey);
  }
  return "—";
}

/**
 * Returns the seat key with the lowest *non-zero* totalUsageToday.
 */
export function getLeastUsedSeat(seatsData) {
  let minKey = null;
  let minVal = Infinity;

  for (const [key, seat] of Object.entries(seatsData)) {
    const usage = num(seat.totalUsageToday);
    if (usage > 0 && usage < minVal) {
      minVal = usage;
      minKey = key;
    }
  }

  if (minKey && minVal < Infinity) {
    return formatSeatName(minKey);
  }
  return "—";
}

/**
 * Average totalUsageToday across all seats.
 */
export function getAverageUsageTime(seatsData) {
  const entries = Object.values(seatsData);
  if (entries.length === 0) return "—";

  const total = entries.reduce((sum, s) => sum + num(s.totalUsageToday), 0);
  const avg = total / entries.length;
  return fmtDuration(avg);
}

/**
 * Occupancy rate = occupied / total * 100
 */
export function getOccupancyRate(summaryData) {
  if (!summaryData) return 0;
  const occupied = num(summaryData.occupiedSeats) + num(summaryData.bagDetectedSeats);
  const total    = num(summaryData.totalSeats) || 4;
  return Math.round((occupied / total) * 100);
}

/**
 * Per-seat utilisation percentage.
 * utilisation = totalUsageToday / totalPossibleSeconds * 100
 */
export function getSeatUtilization(seatData, totalPossibleSeconds = TOTAL_POSSIBLE_SECONDS) {
  const usage = num(seatData.totalUsageToday);
  if (totalPossibleSeconds <= 0) return 0;
  return Math.min(100, Math.round((usage / totalPossibleSeconds) * 100));
}

/**
 * Computes all analytics from seats and summary data.
 */
export function calculateAnalytics(seatsData, summaryData) {
  return {
    mostUsed:      getMostUsedSeat(seatsData),
    leastUsed:     getLeastUsedSeat(seatsData),
    avgUsage:      getAverageUsageTime(seatsData),
    occupancyRate: getOccupancyRate(summaryData),
  };
}

// ── Rendering Functions ───────────────────────────────────────

/**
 * Renders per-seat utilisation bar chart.
 */
export function renderUtilizationBars(seatsData) {
  for (let i = 1; i <= 4; i++) {
    const key  = `Seat${i}`;
    const seat = seatsData[key];
    const bar  = document.getElementById(`utilBar-${i}`);
    const val  = document.getElementById(`utilVal-${i}`);

    if (!bar || !val) continue;

    const pct = seat ? getSeatUtilization(seat) : 0;

    // Animate height with a slight delay per bar for stagger effect
    setTimeout(() => {
      bar.style.height = `${pct}%`;
      val.textContent  = `${pct}%`;
    }, i * 80);
  }
}

/**
 * Renders daily usage comparison bar chart (in minutes).
 */
export function renderDailyUsageChart(seatsData) {
  // Find the max usage for scaling
  let maxUsage = 0;
  for (let i = 1; i <= 4; i++) {
    const key  = `Seat${i}`;
    const seat = seatsData[key];
    const usage = seat ? num(seat.totalUsageToday) : 0;
    if (usage > maxUsage) maxUsage = usage;
  }

  // Avoid division by zero; if no usage yet use 1 as baseline
  const scale = maxUsage > 0 ? maxUsage : 1;

  for (let i = 1; i <= 4; i++) {
    const key  = `Seat${i}`;
    const seat = seatsData[key];
    const bar  = document.getElementById(`dailyBar-${i}`);
    const val  = document.getElementById(`dailyVal-${i}`);

    if (!bar || !val) continue;

    const usageSec = seat ? num(seat.totalUsageToday) : 0;
    const usageMin = Math.round(usageSec / 60);
    const pct      = Math.round((usageSec / scale) * 100);

    setTimeout(() => {
      bar.style.height = `${Math.max(pct, 1)}%`;
      val.textContent  = `${usageMin}m`;
    }, i * 80);
  }
}

/**
 * Master update — refreshes KPI tiles and all charts.
 */
export function updateAnalyticsPanel(seatsData, summaryData) {
  if (!seatsData) return;

  const analytics = calculateAnalytics(seatsData, summaryData);

  // KPI tiles
  setText("mostUsedSeat",  analytics.mostUsed);
  setText("leastUsedSeat", analytics.leastUsed);
  setText("avgUsageTime",  analytics.avgUsage);
  setText("occupancyRate", `${analytics.occupancyRate}%`);

  // Charts
  renderUtilizationBars(seatsData);
  renderDailyUsageChart(seatsData);
}

// ── Private Helpers ───────────────────────────────────────────

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

/**
 * Converts "Seat1" → "Seat 1"
 */
function formatSeatName(key) {
  return key.replace(/([a-zA-Z]+)(\d+)/, "$1 $2");
}

// ── Gender Analytics Functions ────────────────────────────────

/**
 * Aggregates gender session counts across all seats.
 * Returns { male, female, total }
 */
export function getGenderDistribution(seatsData) {
  let male = 0;
  let female = 0;

  for (const seat of Object.values(seatsData)) {
    if (seat.genderStats) {
      male   += num(seat.genderStats.maleCount);
      female += num(seat.genderStats.femaleCount);
    }
  }

  return { male, female, total: male + female };
}

/**
 * Renders the gender distribution donut chart.
 */
export function renderGenderDonut(seatsData) {
  const ring  = document.getElementById("genderDonutRing");
  const total = document.getElementById("genderDonutTotal");
  if (!ring) return;

  const dist = getGenderDistribution(seatsData);

  if (dist.total === 0) {
    ring.style.background = `conic-gradient(var(--text-muted) 0% 100%)`;
    if (total) total.textContent = "0";
    return;
  }

  const malePct = (dist.male / dist.total) * 100;

  ring.style.background = `conic-gradient(
    var(--gender-male)   0% ${malePct}%,
    var(--gender-female) ${malePct}% 100%
  )`;

  if (total) total.textContent = dist.total;
}

/**
 * Renders per-seat gender breakdown horizontal stacked bars.
 */
export function renderGenderBreakdownBars(seatsData) {
  for (let i = 1; i <= 4; i++) {
    const key  = `Seat${i}`;
    const seat = seatsData[key];
    const maleBar   = document.getElementById(`genderBarMale-${i}`);
    const femaleBar = document.getElementById(`genderBarFemale-${i}`);
    const valEl     = document.getElementById(`genderBarVal-${i}`);

    if (!maleBar || !femaleBar || !valEl) continue;

    const m = seat?.genderStats ? num(seat.genderStats.maleCount)   : 0;
    const f = seat?.genderStats ? num(seat.genderStats.femaleCount) : 0;
    const t = m + f;

    const mPct = t > 0 ? (m / t) * 100 : 0;
    const fPct = t > 0 ? (f / t) * 100 : 0;

    setTimeout(() => {
      maleBar.style.width   = `${mPct}%`;
      femaleBar.style.width = `${fPct}%`;
      valEl.textContent     = `${m}M / ${f}F`;
    }, i * 80);
  }
}

/**
 * Master update for the gender analytics section.
 */
export function updateGenderAnalyticsPanel(seatsData) {
  if (!seatsData) return;

  const dist = getGenderDistribution(seatsData);

  // KPI tiles
  setText("totalMaleCount",   dist.male);
  setText("totalFemaleCount", dist.female);

  if (dist.total > 0) {
    setText("maleRatio",   `${Math.round((dist.male / dist.total) * 100)}%`);
    setText("femaleRatio", `${Math.round((dist.female / dist.total) * 100)}%`);
  } else {
    setText("maleRatio",   "—");
    setText("femaleRatio", "—");
  }

  // Charts
  renderGenderDonut(seatsData);
  renderGenderBreakdownBars(seatsData);
}

