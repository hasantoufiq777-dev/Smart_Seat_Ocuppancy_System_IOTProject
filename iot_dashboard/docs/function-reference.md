# 📖 Function Reference — Smart Study Space Occupancy System

> Complete API reference for all functions, constants, and types added to `espcode/espcode.ino` for Firebase integration, usage tracking, and NTP time synchronization.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Constants](#constants)
- [WiFi Functions](#wifi-functions)
- [Firebase Functions](#firebase-functions)
- [Timer Functions](#timer-functions)
- [Utility Functions](#utility-functions)
- [Data Flow Diagram](#data-flow-diagram)

---

## Architecture Overview

The ESP32 firmware is organized into four functional layers:

| Layer | Functions | Phase |
|-------|-----------|-------|
| **WiFi** | `initWiFi()` | `setup()` |
| **Firebase** | `initFirebase()`, `updateSeatFirebase()`, `updateSummaryFirebase()`, `updateSoundFirebase()` | `setup()` + `loop()` |
| **Timers** | `updateSeatTimers()`, `checkDailyReset()` | `loop()` |
| **Utility** | `getStateString()`, `getISOTimestamp()`, `getEpochTime()` | Helpers (called internally) |

---

## Constants

Configuration constants defined at the top of `espcode.ino`. All must be set before flashing.

---

### `WIFI_SSID`

```cpp
#define WIFI_SSID "YourWiFiNetworkName"
```

| Property | Value |
|----------|-------|
| **Type** | `String` (macro) |
| **Purpose** | WiFi network name (SSID) to connect to |
| **Constraints** | Must be a 2.4 GHz network. ESP32 does not support 5 GHz |
| **Used by** | `initWiFi()` |

---

### `WIFI_PASSWORD`

```cpp
#define WIFI_PASSWORD "YourWiFiPassword"
```

| Property | Value |
|----------|-------|
| **Type** | `String` (macro) |
| **Purpose** | WiFi network password (WPA2-PSK) |
| **Constraints** | Case-sensitive |
| **Used by** | `initWiFi()` |

---

### `API_KEY`

```cpp
#define API_KEY "AIzaSyB....................."
```

| Property | Value |
|----------|-------|
| **Type** | `String` (macro) |
| **Purpose** | Firebase Web API key for authentication |
| **Where to find** | Firebase Console → Project Settings → General → Web API Key |
| **Used by** | `initFirebase()` |

---

### `DATABASE_URL`

```cpp
#define DATABASE_URL "https://smartstudyspace-xxxxx-default-rtdb.firebaseio.com/"
```

| Property | Value |
|----------|-------|
| **Type** | `String` (macro) |
| **Purpose** | Firebase Realtime Database URL |
| **Format** | Must start with `https://` and end with `/` |
| **Where to find** | Firebase Console → Realtime Database → URL at top of page |
| **Used by** | `initFirebase()`, all `update*Firebase()` functions |

---

### `USER_EMAIL`

```cpp
#define USER_EMAIL "esp32@smartstudyspace.local"
```

| Property | Value |
|----------|-------|
| **Type** | `String` (macro) |
| **Purpose** | Email address for Firebase email/password authentication |
| **Setup** | Must be created in Firebase Console → Authentication → Users |
| **Used by** | `initFirebase()` |

---

### `USER_PASSWORD`

```cpp
#define USER_PASSWORD "SecurePass123!"
```

| Property | Value |
|----------|-------|
| **Type** | `String` (macro) |
| **Purpose** | Password for Firebase email/password authentication |
| **Setup** | Set when creating the user in Firebase Console |
| **Used by** | `initFirebase()` |

---

### `FIREBASE_UPDATE_INTERVAL`

```cpp
#define FIREBASE_UPDATE_INTERVAL 1000
```

| Property | Value |
|----------|-------|
| **Type** | `int` (macro) |
| **Purpose** | Minimum milliseconds between consecutive Firebase writes |
| **Default** | `1000` (1 second) |
| **Rationale** | Prevents flooding Firebase with rapid state changes. Protects against exceeding the free-tier write quota (100 simultaneous connections, ~10 writes/sec recommended) |
| **Used by** | `updateSeatFirebase()`, `updateSummaryFirebase()`, `updateSoundFirebase()` |

> [!TIP]
> If the ESP32 crashes or restarts frequently, try increasing this value to `2000` or `3000`.

---

### `NTP_SERVER`

```cpp
#define NTP_SERVER "pool.ntp.org"
```

| Property | Value |
|----------|-------|
| **Type** | `String` (macro) |
| **Purpose** | NTP server address for time synchronization |
| **Default** | `"pool.ntp.org"` |
| **Alternatives** | `"time.nist.gov"`, `"time.google.com"` |
| **Used by** | `getISOTimestamp()`, `getEpochTime()`, `checkDailyReset()` |

---

## WiFi Functions

---

### `initWiFi()`

**Phase:** `setup()` — called once at startup

```cpp
void initWiFi()
```

| Property | Details |
|----------|---------|
| **Parameters** | None |
| **Returns** | `void` |
| **Blocks** | Yes — loops until WiFi is connected |

#### Description

Connects the ESP32 to the WiFi network specified by `WIFI_SSID` and `WIFI_PASSWORD`. Uses `WiFi.begin()` to initiate the connection and blocks execution with a retry loop until `WiFi.status()` returns `WL_CONNECTED`. Once connected, prints the assigned local IP address to the Serial Monitor.

This function should only be called during `setup()`. It is a blocking function — the firmware will not proceed to Firebase initialization or the main loop until WiFi is established.

#### Serial Output

```
Connecting to WiFi...
...
Connected to WiFi
IP Address: 192.168.1.105
```

#### Example Usage

```cpp
void setup() {
  Serial.begin(115200);

  // Step 1: Connect to WiFi (blocks until connected)
  initWiFi();

  // Step 2: Initialize Firebase (requires WiFi)
  initFirebase();

  // ... rest of setup
}
```

#### Notes

- Does not implement a timeout — will retry indefinitely. Consider adding a watchdog timer for production deployments.
- If WiFi disconnects during operation, the Firebase library handles reconnection internally.

---

## Firebase Functions

---

### `initFirebase()`

**Phase:** `setup()` — called once after `initWiFi()`

```cpp
void initFirebase()
```

| Property | Details |
|----------|---------|
| **Parameters** | None |
| **Returns** | `void` |
| **Prerequisites** | WiFi must be connected (`initWiFi()` called first) |

#### Description

Initializes the Firebase connection and configures authentication. Performs the following steps:

1. Sets the Firebase **API key** (`API_KEY`) and **database URL** (`DATABASE_URL`) on the config object.
2. Configures **email/password authentication** using `USER_EMAIL` and `USER_PASSWORD`.
3. Sets the **token status callback** to monitor authentication state.
4. Enables **automatic WiFi reconnection** so Firebase can recover from temporary network drops.
5. Calls `Firebase.begin()` to start the Firebase client.
6. Configures NTP time synchronization via `configTime()` using `NTP_SERVER` — required for valid authentication tokens.

#### Serial Output

```
Initializing Firebase...
Firebase client initialized
NTP time synced
```

#### Example Usage

```cpp
void setup() {
  Serial.begin(115200);
  initWiFi();

  // Initialize Firebase after WiFi is ready
  initFirebase();

  // Firebase is now ready for read/write operations
}
```

#### Notes

- Must be called **after** `initWiFi()` — Firebase requires an active network connection.
- The Firebase library manages token refresh in the background. No manual token renewal is needed.
- NTP time sync is critical — Firebase authentication tokens include timestamps and will be rejected if the ESP32 clock is not synchronized.

---

### `updateSeatFirebase(int seatIndex)`

**Phase:** `loop()` — called on seat state or value change

```cpp
void updateSeatFirebase(int seatIndex)
```

| Property | Details |
|----------|---------|
| **Parameters** | `seatIndex` (`int`) — zero-based seat index (0–3 for 4 seats) |
| **Returns** | `void` |
| **Trigger** | Called when a specific seat's state or sensor value changes |

#### Description

Updates the Firebase Realtime Database node for a single seat. Writes the following fields to the path `SmartStudySpace/Seats/Seat{N}/` (where N = seatIndex + 1):

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `status` | `string` | Current seat state | `"AVAILABLE"`, `"OCCUPIED"`, `"BAG_DETECTED"` |
| `fsrValue` | `int` | Raw FSR analog reading (0–4095) | `1250` |
| `humanDetected` | `bool` | IR sensor result (`true` if person detected) | `true` |
| `lastUpdate` | `string` | ISO 8601 timestamp of this update | `"2026-07-08T22:45:00Z"` |
| `startTime` | `string` | ISO timestamp when current OCCUPIED session started | `"2026-07-08T14:30:00Z"` |
| `endTime` | `string` | ISO timestamp when last OCCUPIED session ended | `"2026-07-08T15:45:00Z"` |
| `currentUsage` | `int` | Duration of current OCCUPIED session in seconds | `4500` |
| `totalUsageToday` | `int` | Cumulative OCCUPIED time today in seconds | `12600` |
| `occupancyCount` | `int` | Number of times this seat was occupied today | `5` |

#### Firebase Path

```
SmartStudySpace/
  Seats/
    Seat1/
      status: "OCCUPIED"
      fsrValue: 1250
      humanDetected: true
      lastUpdate: "2026-07-08T22:45:00Z"
      startTime: "2026-07-08T14:30:00Z"
      endTime: ""
      currentUsage: 4500
      totalUsageToday: 12600
      occupancyCount: 5
```

#### Example Usage

```cpp
void loop() {
  // ... read sensors, evaluate states ...

  for (int i = 0; i < NUM_SEATS; i++) {
    SeatState newState = evaluateState(weightDetected, humanDetected);

    if (newState != currentState[i] || fsrValues[i] != lastFsrValues[i]) {
      currentState[i] = newState;
      updateSeatFirebase(i);  // Only update the seat that changed
    }
  }
}
```

#### Notes

- Uses `FIREBASE_UPDATE_INTERVAL` to throttle writes — if called more frequently than the interval, the update is skipped.
- The `seatIndex` is zero-based (0–3), but the Firebase node uses one-based naming (`Seat1`–`Seat4`).
- Uses `Firebase.RTDB.setJSON()` to write all fields atomically in a single request.

---

### `updateSummaryFirebase()`

**Phase:** `loop()` — called when any seat state changes

```cpp
void updateSummaryFirebase()
```

| Property | Details |
|----------|---------|
| **Parameters** | None |
| **Returns** | `void` |
| **Trigger** | Called whenever any seat transitions to a new state |

#### Description

Counts the number of seats in each state and writes a summary to the `SmartStudySpace/Summary/` node. This provides a pre-computed overview for the dashboard, eliminating the need for client-side aggregation.

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `availableSeats` | `int` | Count of seats in AVAILABLE state | `2` |
| `occupiedSeats` | `int` | Count of seats in OCCUPIED state | `1` |
| `bagDetectedSeats` | `int` | Count of seats in BAG state | `1` |
| `totalSeats` | `int` | Total number of seats (always `NUM_SEATS`) | `4` |

#### Firebase Path

```
SmartStudySpace/
  Summary/
    availableSeats: 2
    occupiedSeats: 1
    bagDetectedSeats: 1
    totalSeats: 4
```

#### Example Usage

```cpp
void loop() {
  bool anyStateChanged = false;

  for (int i = 0; i < NUM_SEATS; i++) {
    SeatState newState = evaluateState(weightDetected, humanDetected);
    if (newState != currentState[i]) {
      currentState[i] = newState;
      updateSeatFirebase(i);
      anyStateChanged = true;
    }
  }

  if (anyStateChanged) {
    updateSummaryFirebase();  // Recalculate and push summary
  }
}
```

#### Notes

- Iterates through all `currentState[]` entries to count each state.
- Always writes `totalSeats` as `NUM_SEATS` (currently 4).
- Called **after** all seat states have been evaluated in a given loop iteration, not once per seat.

---

### `updateSoundFirebase(int level, bool isNoisy)`

**Phase:** `loop()` — called when sound status changes

```cpp
void updateSoundFirebase(int level, bool isNoisy)
```

| Property | Details |
|----------|---------|
| **Parameters** | `level` (`int`) — raw analog sound reading (0–4095); `isNoisy` (`bool`) — `true` if level exceeds `SOUND_THRESHOLD` |
| **Returns** | `void` |
| **Trigger** | Called when the sound status transitions (quiet→noisy or noisy→quiet) |

#### Description

Writes the current sound level and status to the `SmartStudySpace/Sound/` node. Only called when the noise state **changes** (not on every loop iteration), to minimize Firebase writes.

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `level` | `int` | Raw analog reading from sound sensor | `450` |
| `status` | `string` | Human-readable noise status | `"Noisy"` or `"Quiet"` |

#### Firebase Path

```
SmartStudySpace/
  Sound/
    level: 450
    status: "Noisy"
```

#### Example Usage

```cpp
void loop() {
  int soundValue = analogRead(SOUND_PIN);
  bool isNoisy = (soundValue > SOUND_THRESHOLD);

  // Only update Firebase when noise state transitions
  if (isNoisy != buzzerActive) {
    buzzerActive = isNoisy;
    updateSoundFirebase(soundValue, isNoisy);
  }
}
```

#### Notes

- The `status` string is derived from `isNoisy`: `true` → `"Noisy"`, `false` → `"Quiet"`.
- Uses `SOUND_THRESHOLD` (default 300) as the boundary.
- Unlike seat updates, sound updates carry only two fields and are lightweight writes.

---

## Timer Functions

---

### `updateSeatTimers()`

**Phase:** `loop()` — called every iteration

```cpp
void updateSeatTimers()
```

| Property | Details |
|----------|---------|
| **Parameters** | None |
| **Returns** | `void` |
| **Call frequency** | Every `loop()` iteration |

#### Description

Manages occupancy timing for all seats. Called every loop iteration, it tracks three transitions for each seat:

#### State Machine

```
┌─────────────┐   state changes   ┌───────────────┐
│  NOT        │  ──to OCCUPIED──► │   OCCUPIED     │
│  OCCUPIED   │                   │                │
│             │ ◄──from OCCUPIED──│  (timing...)   │
└─────────────┘   state changes   └───────────────┘
```

| Transition | Action |
|------------|--------|
| **→ OCCUPIED** (just became occupied) | Records `startTime` (ISO timestamp), increments `occupancyCount` |
| **Remains OCCUPIED** | Updates `currentUsage` (elapsed seconds since `startTime`) |
| **OCCUPIED →** (just left occupied) | Records `endTime`, adds session duration to `totalUsageToday`, clears `currentUsage` to 0 |

#### Tracked Fields Per Seat

| Field | Updated When | Reset When |
|-------|-------------|------------|
| `startTime` | Seat enters OCCUPIED | Never (overwritten on next session) |
| `endTime` | Seat leaves OCCUPIED | Never (overwritten on next session) |
| `currentUsage` | Every loop while OCCUPIED | When seat leaves OCCUPIED |
| `totalUsageToday` | When session ends (adds duration) | Daily reset via `checkDailyReset()` |
| `occupancyCount` | When seat enters OCCUPIED (+1) | Daily reset via `checkDailyReset()` |

#### Example Usage

```cpp
void loop() {
  // ... read sensors, evaluate states ...

  updateSeatTimers();  // Always called — manages timing for all seats

  // ... Firebase updates, sound processing ...
  delay(200);
}
```

#### Notes

- Uses `getEpochTime()` to calculate durations and `getISOTimestamp()` for human-readable timestamps.
- Compares `currentState[i]` against a stored `previousState[i]` array to detect transitions.
- Does **not** write to Firebase directly — the calling code decides when to push updated timer values via `updateSeatFirebase()`.

---

### `checkDailyReset()`

**Phase:** `loop()` — called every iteration (lightweight check)

```cpp
void checkDailyReset()
```

| Property | Details |
|----------|---------|
| **Parameters** | None |
| **Returns** | `void` |
| **Call frequency** | Every `loop()` iteration |

#### Description

Uses NTP-synced time to detect when the calendar day has changed (midnight rollover). When a new day is detected, resets the following fields for **all seats**:

| Field | Reset Value |
|-------|-------------|
| `totalUsageToday` | `0` |
| `occupancyCount` | `0` |

#### How It Works

1. Gets the current day-of-year from `getEpochTime()`.
2. Compares against a stored `lastDay` variable.
3. If the day has changed, resets all per-seat daily counters and updates `lastDay`.

#### Example Usage

```cpp
void loop() {
  checkDailyReset();      // Check if we've crossed midnight
  updateSeatTimers();     // Then update timers (with potentially reset counters)

  // ... rest of loop
}
```

#### Notes

- The NTP time must be synchronized for this to work correctly. If NTP sync fails at startup, the daily reset may not trigger on time.
- Uses GMT/UTC by default. To use a local timezone, adjust the `configTime()` offset in `initFirebase()`.
- The reset is instantaneous — all seats are reset in the same loop iteration.

---

## Utility Functions

---

### `getStateString(SeatState state)`

**Phase:** Utility — called by Firebase update functions

```cpp
const char* getStateString(SeatState state)
```

| Property | Details |
|----------|---------|
| **Parameters** | `state` (`SeatState`) — enum value to convert |
| **Returns** | `const char*` — string representation of the state |

#### Description

Converts a `SeatState` enum value to its string representation for Firebase storage and Serial output.

#### Mapping

| Enum Value | Returned String |
|------------|----------------|
| `AVAILABLE` | `"AVAILABLE"` |
| `OCCUPIED` | `"OCCUPIED"` |
| `BAG` | `"BAG_DETECTED"` |

#### Example Usage

```cpp
SeatState state = evaluateState(weightDetected, humanDetected);

// Used in Firebase updates
Firebase.RTDB.setString(&fbdo, path + "/status", getStateString(state));

// Used in Serial output
Serial.print("Seat 1 is: ");
Serial.println(getStateString(state));
```

#### Notes

- The `BAG` enum maps to the string `"BAG_DETECTED"` (not `"BAG"`) for clarity in the dashboard and Firebase Console.
- Returns a `const char*` (string literal), not a `String` object — safe and memory-efficient.

---

### `getISOTimestamp()`

**Phase:** Utility — called by Firebase update and timer functions

```cpp
String getISOTimestamp()
```

| Property | Details |
|----------|---------|
| **Parameters** | None |
| **Returns** | `String` — current time in ISO 8601 format |

#### Description

Returns the current date and time as an ISO 8601 formatted string using the NTP-synced system clock. The format is:

```
YYYY-MM-DDTHH:MM:SSZ
```

#### Example Output

```
"2026-07-08T22:45:00Z"
```

#### Example Usage

```cpp
// Record when a seat became occupied
String startTime = getISOTimestamp();
Firebase.RTDB.setString(&fbdo, path + "/startTime", startTime);

// Timestamp each Firebase update
Firebase.RTDB.setString(&fbdo, path + "/lastUpdate", getISOTimestamp());
```

#### Notes

- Returns UTC time (denoted by the trailing `Z`).
- Depends on successful NTP synchronization via `configTime()`. If NTP has not synced, returns the epoch start date (`1970-01-01T00:00:00Z`).
- Uses the C `struct tm` and `strftime()` internally.

---

### `getEpochTime()`

**Phase:** Utility — called by timer functions

```cpp
unsigned long getEpochTime()
```

| Property | Details |
|----------|---------|
| **Parameters** | None |
| **Returns** | `unsigned long` — current Unix epoch time in seconds |

#### Description

Returns the current Unix epoch time (seconds since January 1, 1970 00:00:00 UTC) from the NTP-synced system clock. Used for duration calculations in timer functions.

#### Example Output

```
1783720500
```

#### Example Usage

```cpp
// Calculate how long a seat has been occupied
unsigned long sessionStart = getEpochTime();

// ... later ...
unsigned long elapsed = getEpochTime() - sessionStart;
Serial.print("Occupied for ");
Serial.print(elapsed);
Serial.println(" seconds");

// Check day rollover
int currentDay = getEpochTime() / 86400;  // Days since epoch
```

#### Notes

- Returns `0` if NTP has not yet synchronized.
- Precision is ±1 second (NTP accuracy is typically much better than this, but the ESP32 internal clock may drift between syncs).
- Used by `updateSeatTimers()` for `currentUsage` calculation and `checkDailyReset()` for day-change detection.

---

## Data Flow Diagram

```
┌─────────────┐     ┌──────────────┐     ┌──────────────────────────────────┐
│   Sensors   │     │    ESP32     │     │      Firebase RTDB               │
│             │     │              │     │                                  │
│  FSR ───────┼────►│ readFSR()    │     │  SmartStudySpace/                │
│  IR  ───────┼────►│ evaluateState│     │  ├── Seats/                     │
│  Sound ─────┼────►│              │     │  │   ├── Seat1/ ◄───────────────┤
│             │     │      │       │     │  │   ├── Seat2/ ◄─── update-    │
└─────────────┘     │      ▼       │     │  │   ├── Seat3/     SeatFB()   │
                    │ State Change?│     │  │   └── Seat4/ ◄───────────────┤
                    │      │       │     │  │                              │
                    │    Yes│       │     │  ├── Summary/ ◄── update-      │
                    │      ▼       │     │  │                SummaryFB()   │
                    │ updateSeat-  ├────►│  │                              │
                    │ Firebase()   │     │  └── Sound/ ◄──── update-       │
                    │ updateSum-   ├────►│                   SoundFB()     │
                    │ maryFirebase │     │                                  │
                    │ updateSound- ├────►│                                  │
                    │ Firebase()   │     └───────────┬──────────────────────┘
                    │              │                 │
                    │ updateSeat-  │                 │  Real-time sync
                    │ Timers()     │                 ▼
                    │ checkDaily-  │     ┌──────────────────────┐
                    │ Reset()      │     │    Web Dashboard     │
                    └──────────────┘     │  (firebase-config.js)│
                                        │                      │
                                        │  Seats → Cards/Table │
                                        │  Summary → Counters  │
                                        │  Sound → Indicator   │
                                        └──────────────────────┘
```

---

## Function Call Sequence

### `setup()` Phase

```
setup()
  ├── Serial.begin(115200)
  ├── initWiFi()              ← Blocks until WiFi connected
  ├── initFirebase()           ← Configures auth, NTP, Firebase client
  ├── [read initial sensors]
  ├── updateSeatFirebase(0..3) ← Push initial state for all seats
  ├── updateSummaryFirebase()  ← Push initial summary
  └── updateSoundFirebase()    ← Push initial sound level
```

### `loop()` Phase

```
loop()
  ├── [read IR sensors]
  ├── [read FSR sensors]
  ├── evaluateState() for each seat
  │
  ├── checkDailyReset()        ← Check midnight rollover
  ├── updateSeatTimers()       ← Update timing for all seats
  │
  ├── for each seat with state change:
  │     ├── updateSeatFirebase(i)
  │     └── anyStateChanged = true
  │
  ├── if anyStateChanged:
  │     └── updateSummaryFirebase()
  │
  ├── [read sound sensor]
  ├── if sound state changed:
  │     └── updateSoundFirebase(level, isNoisy)
  │
  └── delay(200)
```

---

## Existing Functions (Pre-Firebase)

These functions exist in the original `espcode.ino` and are used alongside the new Firebase functions:

| Function | Description |
|----------|-------------|
| `readFSR(int pin)` | Reads FSR sensor with multi-sample averaging and minimum threshold filtering |
| `evaluateState(bool weightDetected, bool humanDetected)` | Determines seat state from sensor inputs using the truth table |
| `printSeatsStatus(const int[], const int[], int)` | Prints formatted seat status table to Serial Monitor |

These functions remain unchanged and continue to serve their original purpose.
