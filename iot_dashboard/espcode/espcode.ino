//=========================================================
// Smart Study Space Occupancy System (4 Seats + Sound)
//=========================================================
//
// Truth Table:
//   IR pin LOW (0) = human detected
//   IR pin HIGH (1) = no human
//
//   Weight | Human | Result
//   -------|-------|------------
//     0    |   X   | AVAILABLE
//     1    |  Yes  | OCCUPIED
//     1    |  No   | BAG
//
//=========================================================
// Phase : Firebase Integration
// Phase : Timer & Analytics
//=========================================================

#include <WiFi.h>
#include <Firebase_ESP_Client.h>
#include <time.h>

// Firebase helper includes
#include "addons/TokenHelper.h"
#include "addons/RTDBHelper.h"

//=========================================================
// CONFIGURATION — Fill in your credentials
//=========================================================
#define WIFI_SSID        "Redmi Note 12"
#define WIFI_PASSWORD    "87654321"

#define API_KEY          "AIzaSyCO3tKfObKHZ2fCyFPY4m7Eh_4wZTh3TIY"
#define DATABASE_URL     "https://smartstudyspace-library-default-rtdb.asia-southeast1.firebasedatabase.app"

// Database Secret (Legacy token) — Recommended for reliable IoT connection.
//  in Firebase Console -> Project Settings -> Service Accounts -> Database Secrets.
#define DATABASE_SECRET  "gj7rL4gQzWYKMZQrr1AExnmAku9ylbFYujVzFOXq" 

// For email/password auth (optional, uncomment to use):
// #define USER_EMAIL    "esp32@ssos.com"
// #define USER_PASSWORD "31064649"

// NTP Configuration for timestamps
#define NTP_SERVER       "pool.ntp.org"
#define GMT_OFFSET_SEC   21600   // UTC+6 (adjust for your timezone)
#define DST_OFFSET_SEC   0

//=========================================================
// TIMING CONSTANTS (non-blocking)
//=========================================================
#define SENSOR_READ_INTERVAL     200    // ms between sensor reads
#define FIREBASE_UPDATE_INTERVAL 1000   // ms minimum between Firebase writes
#define SOUND_UPDATE_INTERVAL    2000   // ms between sound Firebase writes
#define NTP_SYNC_INTERVAL        3600000 // ms between NTP re-syncs (1 hour)

//=========================================================
// HARDWARE CONFIGURATION (unchanged)
//=========================================================
const int NUM_SEATS = 4;

const int fsrPins[NUM_SEATS] = {34, 35, 32, 33};
const int irPins[NUM_SEATS]  = {27, 18, 19, 14};

// Sound sensor and buzzer
const int SOUND_PIN = 36;
const int BUZZER_PIN = 23;
const int SOUND_THRESHOLD = 300;

const int FSR_THRESHOLD = 1200;
const int HYSTERESIS = 80;

const int FSR_MIN_VALID = 50;
const int FSR_SAMPLES = 5;

//=========================================================
// SEAT STATE ENUM (unchanged)
//=========================================================
enum SeatState
{
  AVAILABLE,
  OCCUPIED,
  BAG
};

//=========================================================
// STATE VARIABLES — existing
//=========================================================
SeatState currentState[NUM_SEATS];
bool weightActive[NUM_SEATS];
bool buzzerActive = false;

//=========================================================
// CHANGE DETECTION — Phase 5
// Track previous values to avoid unnecessary Firebase writes
//=========================================================
SeatState prevState[NUM_SEATS];
int       prevFsrValue[NUM_SEATS];
bool      prevHumanDetected[NUM_SEATS];
bool      prevSoundStatus = false;
int       prevSoundLevel = 0;

//=========================================================
// TIMER VARIABLES — Phase 7
// Per-seat occupancy timing and analytics
//=========================================================
unsigned long seatStartMillis[NUM_SEATS];     // millis() when seat became OCCUPIED
unsigned long seatTotalUsageMs[NUM_SEATS];    // cumulative usage today (ms)
int           seatOccupancyCount[NUM_SEATS];  // number of occupancies today
bool          seatTimerRunning[NUM_SEATS];    // is this seat's timer active?
int           currentDayOfYear = -1;          // for daily reset detection

//=========================================================
// NON-BLOCKING TIMING
//=========================================================
unsigned long lastSensorRead = 0;
unsigned long lastFirebaseUpdate = 0;
unsigned long lastSoundUpdate = 0;
unsigned long lastNTPSync = 0;

//=========================================================
// FIREBASE OBJECTS
//=========================================================
FirebaseData   fbdo;
FirebaseAuth   auth;
FirebaseConfig config;
bool firebaseReady = false;

//=========================================================
// EXISTING FUNCTION: readFSR (unchanged)
//=========================================================
int readFSR(int pin)
{
  long total = 0;
  for(int s = 0; s < FSR_SAMPLES; s++)
  {
    total += analogRead(pin);
    delayMicroseconds(100);
  }
  int avg = total / FSR_SAMPLES;

  if(avg < FSR_MIN_VALID)
    return 0;

  return avg;
}

//=========================================================
// EXISTING FUNCTION: evaluateState (unchanged)
//=========================================================
SeatState evaluateState(bool weightDetected, bool humanDetected)
{
  if (!weightDetected)
    return AVAILABLE;

  if (humanDetected)
    return OCCUPIED;

  return BAG;
}

//=========================================================
// EXISTING FUNCTION: printSeatsStatus (unchanged)
//=========================================================
void printSeatsStatus(const int fsrValues[], const int irRaw[], int soundValue)
{
  Serial.println("\n=== SEATS STATUS UPDATE ===");
  Serial.println("Seat | FSR Value | IR Pin (raw) | Human? | Status");
  Serial.println("-----|-----------|--------------|--------|------------");
  for(int i = 0; i < NUM_SEATS; i++)
  {
    Serial.print("  ");
    Serial.print(i + 1);
    Serial.print("  |    ");

    if (fsrValues[i] < 10) Serial.print("   ");
    else if (fsrValues[i] < 100) Serial.print("  ");
    else if (fsrValues[i] < 1000) Serial.print(" ");
    Serial.print(fsrValues[i]);
    Serial.print("   |      ");

    Serial.print(irRaw[i]);
    Serial.print("       |  ");

    if (irRaw[i] == LOW)
      Serial.print("Yes ");
    else
      Serial.print(" No ");
    Serial.print("  | ");

    switch(currentState[i])
    {
      case AVAILABLE:
        Serial.println("AVAILABLE");
        break;
      case OCCUPIED:
        Serial.println("OCCUPIED");
        break;
      case BAG:
        Serial.println("BAG DETECTED");
        break;
    }
  }

  Serial.println("---------------------------");
  Serial.print("Sound Level: ");
  Serial.print(soundValue);
  if (soundValue > SOUND_THRESHOLD)
    Serial.println("  >> NOISY!");
  else
    Serial.println("  >> Quiet");
  Serial.println("===========================");
}

//=========================================================
// NEW FUNCTION: getStateString
// Converts SeatState enum to Firebase-friendly string
//=========================================================
String getStateString(SeatState state)
{
  switch(state)
  {
    case AVAILABLE: return "AVAILABLE";
    case OCCUPIED:  return "OCCUPIED";
    case BAG:       return "BAG_DETECTED";
    default:        return "UNKNOWN";
  }
}

//=========================================================
// NEW FUNCTION: getISOTimestamp
// Returns current time as ISO 8601 string via NTP
//=========================================================
String getISOTimestamp()
{
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo))
  {
    return "TIME_NOT_SET";
  }
  char buffer[30];
  strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%S", &timeinfo);
  return String(buffer);
}

//=========================================================
// NEW FUNCTION: getEpochTime
// Returns Unix epoch seconds from NTP-synced clock
//=========================================================
unsigned long getEpochTime()
{
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo))
  {
    return 0;
  }
  time_t now;
  time(&now);
  return (unsigned long)now;
}

//=========================================================
// NEW FUNCTION: getDayOfYear
// Returns day of year (1-366) for daily reset detection
//=========================================================
int getDayOfYear()
{
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo))
  {
    return -1;
  }
  return timeinfo.tm_yday;
}

//=========================================================
// NEW FUNCTION: initWiFi
// Connects ESP32 to WiFi with retry logic
//=========================================================
void initWiFi()
{
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("[WiFi] Connecting to ");
  Serial.print(WIFI_SSID);

  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 30)
  {
    delay(500);
    Serial.print(".");
    retries++;
  }

  if (WiFi.status() == WL_CONNECTED)
  {
    Serial.println();
    Serial.print("[WiFi] Connected! IP: ");
    Serial.println(WiFi.localIP());
  }
  else
  {
    Serial.println();
    Serial.println("[WiFi] FAILED to connect. Check credentials.");
  }
}

//=========================================================
// NEW FUNCTION: initFirebase
// Initializes Firebase RTDB with authentication
//=========================================================
void initFirebase()
{
  config.database_url = DATABASE_URL;

  // If a Database Secret is provided, use it for legacy authentication.
  // This is highly reliable as it bypasses Google OAuth and NTP checks.
  if (String(DATABASE_SECRET).length() > 0)
  {
    config.signer.tokens.legacy_token = DATABASE_SECRET;
    Serial.println("[Firebase] Initializing with Database Secret (Legacy Token)");
  }
  else
  {
    // Fallback: Test mode (requires database rules to be fully public: ".read": true, ".write": true)
    config.signer.test_mode = true;
    Serial.println("[Firebase] Initializing in test mode (unauthenticated)");
  }

  // Set connection parameters
  config.timeout.serverResponse = 10 * 1000;  // 10 second timeout

  Firebase.begin(&config, &auth);
  Firebase.reconnectNetwork(true);

  // Wait for connection
  Serial.print("[Firebase] Connecting");
  unsigned long startMs = millis();
  while (!Firebase.ready() && (millis() - startMs < 5000))
  {
    Serial.print(".");
    delay(300);
  }
  Serial.println();

  firebaseReady = true;
  Serial.println("[Firebase] Initialized successfully.");
}

//=========================================================
// NEW FUNCTION: initNTP
// Synchronizes ESP32 clock via NTP for timestamps
//=========================================================
void initNTP()
{
  configTime(GMT_OFFSET_SEC, DST_OFFSET_SEC, NTP_SERVER);
  Serial.print("[NTP] Syncing time");

  struct tm timeinfo;
  int retries = 0;
  while (!getLocalTime(&timeinfo) && retries < 10)
  {
    Serial.print(".");
    delay(500);
    retries++;
  }
  Serial.println();

  if (retries < 10)
  {
    Serial.print("[NTP] Time: ");
    Serial.println(getISOTimestamp());
    currentDayOfYear = getDayOfYear();
  }
  else
  {
    Serial.println("[NTP] Time sync FAILED. Timestamps may be incorrect.");
  }
}

//=========================================================
// NEW FUNCTION: updateSeatFirebase
// Updates Firebase for a single seat (only changed values)
// Called per-seat to minimize write operations
//=========================================================
void updateSeatFirebase(int seatIndex, int fsrValue, bool humanDetected)
{
  if (!firebaseReady || WiFi.status() != WL_CONNECTED) return;

  String basePath = "/SmartStudySpace/Seats/Seat" + String(seatIndex + 1);

  // Build a JSON object for batch update (single write per seat)
  FirebaseJson json;

  json.set("status", getStateString(currentState[seatIndex]));
  json.set("fsrValue", fsrValue);
  json.set("humanDetected", humanDetected);
  json.set("lastUpdate", getISOTimestamp());

  // Timer data (Phase 7)
  if (seatTimerRunning[seatIndex])
  {
    unsigned long currentUsageSec = (millis() - seatStartMillis[seatIndex]) / 1000;
    json.set("currentUsage", (int)currentUsageSec);
  }
  else
  {
    json.set("currentUsage", 0);
  }

  json.set("totalUsageToday", (int)(seatTotalUsageMs[seatIndex] / 1000));
  json.set("occupancyCount", seatOccupancyCount[seatIndex]);

  // Start/end time strings
  if (seatTimerRunning[seatIndex])
  {
    // startTime was set when timer started
    json.set("endTime", "");
  }

  if (Firebase.RTDB.updateNode(&fbdo, basePath, &json))
  {
    Serial.print("[Firebase] Seat ");
    Serial.print(seatIndex + 1);
    Serial.println(" updated.");
  }
  else
  {
    Serial.print("[Firebase] Seat ");
    Serial.print(seatIndex + 1);
    Serial.print(" update FAILED: ");
    Serial.println(fbdo.errorReason());
  }
}

//=========================================================
// NEW FUNCTION: updateSummaryFirebase
// Counts seats by state and updates Summary node
//=========================================================
void updateSummaryFirebase()
{
  if (!firebaseReady || WiFi.status() != WL_CONNECTED) return;

  int availCount = 0, occCount = 0, bagCount = 0;
  for (int i = 0; i < NUM_SEATS; i++)
  {
    switch(currentState[i])
    {
      case AVAILABLE: availCount++; break;
      case OCCUPIED:  occCount++;   break;
      case BAG:       bagCount++;   break;
    }
  }

  FirebaseJson json;
  json.set("availableSeats", availCount);
  json.set("occupiedSeats", occCount);
  json.set("bagDetectedSeats", bagCount);
  json.set("totalSeats", NUM_SEATS);

  if (Firebase.RTDB.updateNode(&fbdo, "/SmartStudySpace/Summary", &json))
  {
    Serial.println("[Firebase] Summary updated.");
  }
  else
  {
    Serial.print("[Firebase] Summary update FAILED: ");
    Serial.println(fbdo.errorReason());
  }
}

//=========================================================
// NEW FUNCTION: updateSoundFirebase
// Updates Sound node in Firebase
//=========================================================
void updateSoundFirebase(int level, bool isNoisy)
{
  if (!firebaseReady || WiFi.status() != WL_CONNECTED) return;

  FirebaseJson json;
  json.set("level", level);
  json.set("status", isNoisy ? "Noisy" : "Quiet");

  if (Firebase.RTDB.updateNode(&fbdo, "/SmartStudySpace/Sound", &json))
  {
    Serial.println("[Firebase] Sound updated.");
  }
  else
  {
    Serial.print("[Firebase] Sound update FAILED: ");
    Serial.println(fbdo.errorReason());
  }
}

//=========================================================
// NEW FUNCTION: handleSeatTimerTransition
// Manages timer start/stop when seat state changes
// Called for each seat that changed state
//=========================================================
void handleSeatTimerTransition(int seatIndex, SeatState oldState, SeatState newState)
{
  // Transition TO OCCUPIED: start timer
  if (newState == OCCUPIED && oldState != OCCUPIED)
  {
    seatStartMillis[seatIndex] = millis();
    seatTimerRunning[seatIndex] = true;
    seatOccupancyCount[seatIndex]++;

    // Record start time in Firebase
    if (firebaseReady && Firebase.ready())
    {
      String path = "/SmartStudySpace/Seats/Seat" + String(seatIndex + 1) + "/startTime";
      Firebase.RTDB.setString(&fbdo, path, getISOTimestamp());
    }

    Serial.print("[Timer] Seat ");
    Serial.print(seatIndex + 1);
    Serial.println(" timer STARTED.");
  }

  // Transition FROM OCCUPIED: stop timer, accumulate usage
  if (oldState == OCCUPIED && newState != OCCUPIED)
  {
    if (seatTimerRunning[seatIndex])
    {
      unsigned long sessionMs = millis() - seatStartMillis[seatIndex];
      seatTotalUsageMs[seatIndex] += sessionMs;
      seatTimerRunning[seatIndex] = false;

      // Record end time in Firebase
      if (firebaseReady && Firebase.ready())
      {
        String path = "/SmartStudySpace/Seats/Seat" + String(seatIndex + 1) + "/endTime";
        Firebase.RTDB.setString(&fbdo, path, getISOTimestamp());
      }

      Serial.print("[Timer] Seat ");
      Serial.print(seatIndex + 1);
      Serial.print(" timer STOPPED. Session: ");
      Serial.print(sessionMs / 1000);
      Serial.println("s");
    }
  }
}

//=========================================================
// NEW FUNCTION: checkDailyReset
// Resets daily analytics counters at midnight (NTP-based)
//=========================================================
void checkDailyReset()
{
  int today = getDayOfYear();
  if (today < 0) return;  // NTP not yet synced

  if (currentDayOfYear >= 0 && today != currentDayOfYear)
  {
    Serial.println("[Reset] New day detected! Resetting daily counters.");
    for (int i = 0; i < NUM_SEATS; i++)
    {
      seatTotalUsageMs[i] = 0;
      seatOccupancyCount[i] = 0;
    }
    currentDayOfYear = today;
  }
}

//=========================================================
// NEW FUNCTION: updateRunningTimersFirebase
// Periodically pushes currentUsage for seats with running timers
// So the dashboard can show live session duration
//=========================================================
void updateRunningTimersFirebase()
{
  if (!firebaseReady || WiFi.status() != WL_CONNECTED) return;

  for (int i = 0; i < NUM_SEATS; i++)
  {
    if (seatTimerRunning[i])
    {
      unsigned long currentUsageSec = (millis() - seatStartMillis[i]) / 1000;
      String path = "/SmartStudySpace/Seats/Seat" + String(i + 1) + "/currentUsage";
      Firebase.RTDB.setInt(&fbdo, path, (int)currentUsageSec);
    }
  }
}

//=========================================================
// SETUP
//=========================================================
void setup()
{
  Serial.begin(115200);
  Serial.println("\n=========================================");
  Serial.println("  Smart Study Space Occupancy System");
  Serial.println("  Phase 5+6+7: Firebase + Dashboard");
  Serial.println("=========================================\n");

  // --- Hardware setup (unchanged) ---
  for(int i = 0; i < NUM_SEATS; i++)
    pinMode(irPins[i], INPUT_PULLUP);

  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  // --- Initialize state arrays ---
  for(int i = 0; i < NUM_SEATS; i++)
  {
    prevState[i] = AVAILABLE;
    prevFsrValue[i] = 0;
    prevHumanDetected[i] = false;
    seatStartMillis[i] = 0;
    seatTotalUsageMs[i] = 0;
    seatOccupancyCount[i] = 0;
    seatTimerRunning[i] = false;
  }

  // --- Initial sensor read (unchanged logic) ---
  int fsrValues[NUM_SEATS];
  int irRaw[NUM_SEATS];

  for(int i = 0; i < NUM_SEATS; i++)
    irRaw[i] = digitalRead(irPins[i]);

  for(int i = 0; i < NUM_SEATS; i++)
  {
    fsrValues[i] = readFSR(fsrPins[i]);
    bool humanDetected = (irRaw[i] == LOW);
    bool wd = (fsrValues[i] > FSR_THRESHOLD);
    weightActive[i] = wd;
    currentState[i] = evaluateState(wd, humanDetected);
    prevState[i] = currentState[i];
  }

  int soundValue = analogRead(SOUND_PIN);
  printSeatsStatus(fsrValues, irRaw, soundValue);

  // --- Phase 5: Connect to WiFi and Firebase ---
  initWiFi();
  initNTP();
  initFirebase();

  // --- Upload initial state to Firebase ---
  if (firebaseReady)
  {
    for (int i = 0; i < NUM_SEATS; i++)
    {
      bool hd = (irRaw[i] == LOW);
      updateSeatFirebase(i, fsrValues[i], hd);
    }
    updateSummaryFirebase();
    updateSoundFirebase(soundValue, soundValue > SOUND_THRESHOLD);
    Serial.println("[Firebase] Initial state uploaded.");
  }
}

//=========================================================
// LOOP (sensor logic unchanged, Firebase + timers added)
//=========================================================
void loop()
{
  unsigned long now = millis();

  // ----- Non-blocking sensor read interval -----
  if (now - lastSensorRead < SENSOR_READ_INTERVAL)
    return;
  lastSensorRead = now;

  // =============================================
  // EXISTING SENSOR READING LOGIC (unchanged)
  // =============================================
  int fsrValues[NUM_SEATS];
  int irRaw[NUM_SEATS];
  bool anyStateChanged = false;

  // Read all IR pins first (fast)
  for(int i = 0; i < NUM_SEATS; i++)
    irRaw[i] = digitalRead(irPins[i]);

  // Read all FSR pins
  for(int i = 0; i < NUM_SEATS; i++)
  {
    fsrValues[i] = readFSR(fsrPins[i]);

    bool humanDetected = (irRaw[i] == LOW);

    bool weightDetected = weightActive[i];
    if (!weightActive[i] && fsrValues[i] > FSR_THRESHOLD)
    {
      weightDetected = true;
    }
    else if (weightActive[i] && fsrValues[i] < (FSR_THRESHOLD - HYSTERESIS))
    {
      weightDetected = false;
    }
    weightActive[i] = weightDetected;

    SeatState newState = evaluateState(weightDetected, humanDetected);

    if (newState != currentState[i])
    {
      // Phase 7: Handle timer transition BEFORE updating state
      handleSeatTimerTransition(i, currentState[i], newState);

      currentState[i] = newState;
      anyStateChanged = true;
    }
  }

  // Read sound sensor
  int soundValue = analogRead(SOUND_PIN);
  
  // Track last time a noise exceeded the threshold
  static unsigned long lastNoiseTime = 0;
  if (soundValue > SOUND_THRESHOLD)
  {
    lastNoiseTime = now;
  }

  // Sustain "Noisy" state for 3 seconds after last threshold spike to prevent audio stuttering
  bool isNoisy = (now - lastNoiseTime < 3000);

  // Control buzzer
  if (isNoisy)
    digitalWrite(BUZZER_PIN, HIGH);
  else
    digitalWrite(BUZZER_PIN, LOW);

  // Track buzzer state change
  if (isNoisy != buzzerActive)
  {
    buzzerActive = isNoisy;
    anyStateChanged = true;
  }

  // Print table if any seat or sound state changed
  if (anyStateChanged)
  {
    printSeatsStatus(fsrValues, irRaw, soundValue);
  }

  // =============================================
  // PHASE 5: FIREBASE UPDATES (change-driven)
  // =============================================
  if (firebaseReady && WiFi.status() == WL_CONNECTED)
  {
    bool anySeatUpdated = false;

    // Check each seat for changes
    if (now - lastFirebaseUpdate >= FIREBASE_UPDATE_INTERVAL)
    {
      for (int i = 0; i < NUM_SEATS; i++)
      {
        bool humanDetected = (irRaw[i] == LOW);
        bool seatChanged = false;

        // Check if state changed
        if (currentState[i] != prevState[i])
          seatChanged = true;

        // Check if FSR value changed significantly (±50)
        if (abs(fsrValues[i] - prevFsrValue[i]) > 50)
          seatChanged = true;

        // Check if human detection changed
        if (humanDetected != prevHumanDetected[i])
          seatChanged = true;

        if (seatChanged)
        {
          updateSeatFirebase(i, fsrValues[i], humanDetected);
          prevState[i] = currentState[i];
          prevFsrValue[i] = fsrValues[i];
          prevHumanDetected[i] = humanDetected;
          anySeatUpdated = true;
        }
      }

      // Update summary if any seat changed
      if (anySeatUpdated)
      {
        updateSummaryFirebase();
      }

      // Update running timers (live session duration)
      updateRunningTimersFirebase();

      lastFirebaseUpdate = now;
    }

    // Sound state change: write immediately to ensure real-time audio response
    if (isNoisy != prevSoundStatus)
    {
      updateSoundFirebase(soundValue, isNoisy);
      prevSoundStatus = isNoisy;
      prevSoundLevel = soundValue;
    }
    // Sound level variation: throttle updates to reduce database writes
    else if (now - lastSoundUpdate >= SOUND_UPDATE_INTERVAL)
    {
      if (abs(soundValue - prevSoundLevel) > 50)
      {
        updateSoundFirebase(soundValue, isNoisy);
        prevSoundLevel = soundValue;
      }
      lastSoundUpdate = now;
    }

    // Daily reset check (Phase 7)
    if (now - lastNTPSync >= NTP_SYNC_INTERVAL)
    {
      checkDailyReset();
      lastNTPSync = now;
    }
  }
  else if (!firebaseReady)
  {
    // Attempt reconnection periodically
    static unsigned long lastReconnect = 0;
    if (now - lastReconnect > 30000)  // every 30 seconds
    {
      if (WiFi.status() != WL_CONNECTED)
      {
        Serial.println("[WiFi] Reconnecting...");
        WiFi.reconnect();
      }
      if (WiFi.status() == WL_CONNECTED)
      {
        firebaseReady = true;
        Serial.println("[Firebase] Reconnected!");
      }
      lastReconnect = now;
    }
  }
}