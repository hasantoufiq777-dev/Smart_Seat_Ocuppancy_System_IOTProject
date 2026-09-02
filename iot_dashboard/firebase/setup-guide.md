# 🔥 Firebase Setup Guide — Smart Study Space Occupancy System

> Complete step-by-step guide for connecting your ESP32 hardware to Firebase Realtime Database and deploying the web dashboard.

---

## Table of Contents

1. [Create Firebase Project](#1-create-firebase-project)
2. [Enable Realtime Database](#2-enable-realtime-database)
3. [Get Configuration](#3-get-configuration)
4. [Configure ESP32](#4-configure-esp32)
5. [Arduino IDE Setup](#5-arduino-ide-setup)
6. [Deploy Dashboard](#6-deploy-dashboard)
7. [Verify Everything Works](#7-verify-everything-works)
8. [Troubleshooting](#troubleshooting)

---

## 1. Create Firebase Project

### Steps

1. **Open the Firebase Console**
   Navigate to [https://console.firebase.google.com](https://console.firebase.google.com) and sign in with your Google account.

2. **Click "Add project"**
   On the Firebase Console landing page, click the **Add project** card.

   <!-- Screenshot: Firebase Console → Add project button -->

3. **Name your project**
   Enter the project name:
   ```
   SmartStudySpace
   ```
   Firebase will auto-generate a unique project ID below the name (e.g., `smartstudyspace-a1b2c`). You can edit the ID if you wish, but the default is fine.

4. **Disable Google Analytics (optional)**
   On the next screen, toggle **off** "Enable Google Analytics for this project." Analytics is not required for this system and disabling it simplifies setup.

   > [!TIP]
   > If you plan to track dashboard usage later, you can always enable Analytics from Project Settings after creation.

5. **Click "Create project"**
   Wait for Firebase to provision your project (usually 10–20 seconds). Click **Continue** when the "Your new project is ready" message appears.

---

## 2. Enable Realtime Database

### Steps

1. **Open Realtime Database**
   In the left sidebar of the Firebase Console, expand **Build** and click **Realtime Database**.

   <!-- Screenshot: Firebase sidebar → Build → Realtime Database -->

2. **Click "Create Database"**
   Click the **Create Database** button in the center of the page.

3. **Select region**
   Choose your database location. Recommended:
   ```
   United States (us-central1)
   ```

   > [!IMPORTANT]
   > The region **cannot be changed** after creation. Choose the region closest to your ESP32 deployment for lowest latency.

   | Region | Best For |
   |--------|----------|
   | `us-central1` | Americas (default, recommended) |
   | `europe-west1` | Europe, Middle East, Africa |
   | `asia-southeast1` | Asia Pacific |

4. **Start in Test Mode**
   Select **Start in test mode** on the security rules screen. This allows unrestricted read/write access for development.

   > [!WARNING]
   > Test mode rules **expire after 30 days**. You will need to update the rules before expiry. See `database.rules.json` for production rules.

5. **Copy the Database URL**
   After creation, your database URL appears at the top of the Realtime Database page. Copy it — you will need it for both the ESP32 and the dashboard.

   ```
   https://smartstudyspace-xxxxx-default-rtdb.firebaseio.com/
   ```

   > [!NOTE]
   > Your URL will contain your unique project ID. The format is always:
   > `https://<project-id>-default-rtdb.firebaseio.com/`

---

## 3. Get Configuration

### Steps

1. **Go to Project Settings**
   Click the ⚙️ **gear icon** next to "Project Overview" in the top-left sidebar, then select **Project settings**.

   <!-- Screenshot: Firebase Console → Settings gear → Project settings -->

2. **Register a Web App**
   Scroll down to the **"Your apps"** section. Click the **web icon** (`</>`) to add a new web app.

   <!-- Screenshot: Your apps section → Web icon (</>) -->

3. **Enter app nickname**
   Register the app with the name:
   ```
   StudySpaceDashboard
   ```
   You do **not** need to enable Firebase Hosting at this step (we'll cover it separately in Section 6).

   Click **Register app**.

4. **Copy the firebaseConfig object**
   Firebase will display a code snippet containing your configuration. Copy the entire `firebaseConfig` object:

   ```javascript
   const firebaseConfig = {
     apiKey: "AIzaSyB.....................",
     authDomain: "smartstudyspace-xxxxx.firebaseapp.com",
     databaseURL: "https://smartstudyspace-xxxxx-default-rtdb.firebaseio.com",
     projectId: "smartstudyspace-xxxxx",
     storageBucket: "smartstudyspace-xxxxx.appspot.com",
     messagingSenderId: "123456789012",
     appId: "1:123456789012:web:abc123def456"
   };
   ```

5. **Note down these three values** (you'll need them for the ESP32 and dashboard):

   | Value | Where to Find | Used By |
   |-------|--------------|---------|
   | **API Key** | `apiKey` field | ESP32 (`API_KEY` constant) |
   | **Database URL** | `databaseURL` field | ESP32 (`DATABASE_URL` constant) + Dashboard |
   | **Project ID** | `projectId` field | Dashboard config |

### Enable Email/Password Authentication

The ESP32 uses email/password sign-in to authenticate with Firebase. You must enable this provider:

1. Go to **Build → Authentication** in the sidebar.
2. Click **Get started** (if first time).
3. Under the **Sign-in method** tab, click **Email/Password**.
4. **Enable** the first toggle (Email/Password). Leave the "Email link" toggle disabled.
5. Click **Save**.

Then create a user account for the ESP32:

1. Go to the **Users** tab in Authentication.
2. Click **Add user**.
3. Enter an email and password (e.g., `esp32@smartstudyspace.local` / `SecurePass123!`).
4. Click **Add user**.
5. Save these credentials — you'll enter them in the ESP32 code.

---

## 4. Configure ESP32

### Steps

1. **Open the Arduino sketch**
   Open `espcode/espcode.ino` in the Arduino IDE.

2. **Add WiFi credentials**
   Near the top of the file, locate (or add) the WiFi constants and replace with your network credentials:

   ```cpp
   #define WIFI_SSID     "YourWiFiNetworkName"
   #define WIFI_PASSWORD "YourWiFiPassword"
   ```

   > [!IMPORTANT]
   > The ESP32 only supports **2.4 GHz** WiFi networks. 5 GHz networks will not work. If your router broadcasts both bands under the same SSID, ensure the ESP32 can see the 2.4 GHz band, or use a dedicated 2.4 GHz SSID.

3. **Add Firebase credentials**
   Locate (or add) the Firebase constants and replace with your values from Section 3:

   ```cpp
   #define API_KEY       "AIzaSyB....................."
   #define DATABASE_URL  "https://smartstudyspace-xxxxx-default-rtdb.firebaseio.com/"
   ```

4. **Add authentication credentials**
   Enter the email and password you created in the Authentication console:

   ```cpp
   #define USER_EMAIL    "esp32@smartstudyspace.local"
   #define USER_PASSWORD "SecurePass123!"
   ```

   **Why email/password authentication?**

   | Method | Pros | Cons |
   |--------|------|------|
   | **Email/Password** (used here) | Simple, persistent, works on ESP32 | Must create user manually |
   | Anonymous Auth | No credentials needed | Token expires, harder to manage |
   | Service Account | Full admin access | Complex key management on ESP32 |

   The Firebase ESP Client library handles token generation and refresh automatically when you provide email/password credentials. The ESP32 signs in once at startup, and the library manages token renewal in the background.

### Complete Configuration Block

After adding all constants, the top of your `espcode.ino` should include:

```cpp
//=========================================================
// Firebase & WiFi Configuration
//=========================================================
#define WIFI_SSID       "YourWiFiNetworkName"
#define WIFI_PASSWORD   "YourWiFiPassword"

#define API_KEY         "AIzaSyB....................."
#define DATABASE_URL    "https://smartstudyspace-xxxxx-default-rtdb.firebaseio.com/"

#define USER_EMAIL      "esp32@smartstudyspace.local"
#define USER_PASSWORD   "SecurePass123!"

#define FIREBASE_UPDATE_INTERVAL 1000  // Minimum ms between Firebase writes
#define NTP_SERVER      "pool.ntp.org"
```

---

## 5. Arduino IDE Setup

### Step 1: Install ESP32 Board Package

1. Open Arduino IDE.
2. Go to **File → Preferences** (or **Arduino IDE → Settings** on macOS).
3. In the **"Additional Board Manager URLs"** field, paste:
   ```
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```
   If you already have other URLs, separate them with a comma.
4. Click **OK**.
5. Go to **Tools → Board → Boards Manager**.
6. Search for `esp32`.
7. Install **"esp32 by Espressif Systems"** (latest stable version).

   <!-- Screenshot: Boards Manager → esp32 by Espressif Systems → Install -->

### Step 2: Select Board

1. Go to **Tools → Board → esp32**.
2. Select **"ESP32 Dev Module"**.

### Step 3: Install Required Libraries

Open **Tools → Manage Libraries** (or **Sketch → Include Library → Manage Libraries**).

#### Firebase ESP Client (REQUIRED)

1. In the Library Manager search bar, type exactly:
   ```
   Firebase ESP Client
   ```
2. Find **"Firebase ESP Client"** by **Mobizt** (version **4.4.x** or latest).
3. Click **Install**. Accept any dependency prompts.

> [!CAUTION]
> **DO NOT** install the deprecated library called `FirebaseESP32`. It is an older, unmaintained library with a different API. The correct library is **"Firebase ESP Client"** by Mobizt — it supports ESP32, ESP8266, and RP2040.
>
> If you see multiple results, look for the one with the description mentioning "Firebase Realtime Database, Cloud Firestore, Firebase Storage, Cloud Messaging…"

| ✅ Correct Library | ❌ Wrong Library |
|---|---|
| **Firebase ESP Client** by Mobizt | FirebaseESP32 by Mobizt |
| Version 4.4.x+ | (deprecated) |
| Supports RTDB, Firestore, Storage, FCM | RTDB only |

### Step 4: Configure Board Settings

Go to **Tools** and set the following:

| Setting | Value |
|---------|-------|
| **Board** | ESP32 Dev Module |
| **Upload Speed** | 115200 |
| **CPU Frequency** | 240MHz (WiFi/BT) |
| **Flash Frequency** | 80MHz |
| **Flash Mode** | QIO |
| **Flash Size** | 4MB (32Mb) |
| **Partition Scheme** | Default 4MB with spiffs |
| **Port** | (select your ESP32's COM port) |

> [!TIP]
> If no COM port appears, install the CP2102 or CH340 USB-to-serial driver for your specific ESP32 board. Check your board's documentation for which chip it uses.

---

## 6. Deploy Dashboard

### Option A — Local (Quick Start)

Best for development and testing.

1. **Open the dashboard**
   Navigate to the `dashboard/` directory and open `index.html` in any modern web browser (Chrome, Firefox, or Edge recommended).

   ```
   dashboard/index.html
   ```

2. **Edit Firebase configuration**
   Open `dashboard/firebase-config.js` (or the config section in `index.html`) and replace the placeholder values with your Firebase credentials from Section 3:

   ```javascript
   const firebaseConfig = {
     apiKey: "YOUR_API_KEY",
     authDomain: "YOUR_PROJECT_ID.firebaseapp.com",
     databaseURL: "https://YOUR_PROJECT_ID-default-rtdb.firebaseio.com",
     projectId: "YOUR_PROJECT_ID",
     storageBucket: "YOUR_PROJECT_ID.appspot.com",
     messagingSenderId: "YOUR_SENDER_ID",
     appId: "YOUR_APP_ID"
   };
   ```

3. **Open in browser**
   Double-click `index.html` or use a local server:
   ```bash
   # Using Python
   cd dashboard
   python -m http.server 8080

   # Using Node.js
   npx serve dashboard
   ```
   Then open `http://localhost:8080` in your browser.

---

### Option B — Firebase Hosting (Production)

Best for remote access and sharing a public URL.

1. **Install Firebase CLI**
   Requires [Node.js](https://nodejs.org/) (v16+ recommended).

   ```bash
   npm install -g firebase-tools
   ```

   Verify installation:
   ```bash
   firebase --version
   ```

2. **Log in to Firebase**

   ```bash
   firebase login
   ```

   A browser window will open for Google account authentication.

3. **Initialize Firebase Hosting**
   From the project root directory (`iot_dashboard/`):

   ```bash
   firebase init hosting
   ```

   Answer the prompts as follows:

   | Prompt | Answer |
   |--------|--------|
   | Select a project | Use an existing project → `SmartStudySpace` |
   | Public directory | `dashboard` |
   | Configure as single-page app? | **No** |
   | Set up automatic builds with GitHub? | **No** |
   | Overwrite `dashboard/index.html`? | **No** |

4. **Deploy**

   ```bash
   firebase deploy
   ```

5. **Access your dashboard**
   Firebase will output a hosting URL:
   ```
   ✔ Hosting URL: https://smartstudyspace-xxxxx.web.app
   ```

   Your dashboard is now live and accessible from anywhere.

> [!TIP]
> To redeploy after making changes, simply run `firebase deploy` again. Only changed files are uploaded.

---

## 7. Verify Everything Works

Follow this checklist **in order** to confirm your entire system is operational.

### Step 1: Flash the ESP32

1. Connect the ESP32 via USB.
2. Select the correct COM port in **Tools → Port**.
3. Click **Upload** (→ arrow button).
4. Wait for "Done uploading" in the Arduino IDE output.

### Step 2: Open Serial Monitor

1. Go to **Tools → Serial Monitor**.
2. Set baud rate to **115200** (bottom-right dropdown).
3. Press the **RST/EN** button on the ESP32 to restart.

### Step 3: Verify WiFi Connection

Look for output similar to:

```
Connecting to WiFi...
Connected to WiFi
IP Address: 192.168.1.105
```

If you see dots printing endlessly (`....`), WiFi is failing to connect. See [Troubleshooting](#troubleshooting).

### Step 4: Verify Firebase Connection

After WiFi connects, look for:

```
Firebase client initialized
Token ready / Sign-in OK
```

If you see authentication errors, verify your API key, email, and password.

### Step 5: Check Firebase Console

1. Open [Firebase Console](https://console.firebase.google.com) → your project.
2. Go to **Realtime Database**.
3. You should see a **`SmartStudySpace`** node with child nodes:

   ```
   SmartStudySpace/
   ├── Seats/
   │   ├── Seat1/
   │   │   ├── status: "AVAILABLE"
   │   │   ├── fsrValue: 0
   │   │   ├── humanDetected: false
   │   │   ├── lastUpdate: "2026-07-08T22:45:00Z"
   │   │   ├── occupancyCount: 0
   │   │   └── totalUsageToday: 0
   │   ├── Seat2/ ...
   │   ├── Seat3/ ...
   │   └── Seat4/ ...
   ├── Summary/
   │   ├── availableSeats: 4
   │   ├── occupiedSeats: 0
   │   ├── bagDetectedSeats: 0
   │   └── totalSeats: 4
   └── Sound/
       ├── level: 120
       └── status: "Quiet"
   ```

### Step 6: Verify Dashboard

1. Open the dashboard (local or hosted URL).
2. All four seats should appear with their current status.
3. **Test real-time updates**: place weight on an FSR sensor → the dashboard should update within 1–2 seconds.

### ✅ Success Criteria

| Check | Expected Result |
|-------|----------------|
| Serial Monitor shows WiFi IP | ✅ |
| Serial Monitor shows Firebase token | ✅ |
| Firebase Console shows SmartStudySpace node | ✅ |
| Data updates when sensor state changes | ✅ |
| Dashboard reflects real-time data | ✅ |

---

## Troubleshooting

### WiFi Won't Connect

| Symptom | Cause | Fix |
|---------|-------|-----|
| Endless `....` in Serial Monitor | Wrong credentials | Double-check `WIFI_SSID` and `WIFI_PASSWORD` (case-sensitive) |
| Connects then disconnects | 5 GHz network | Use a **2.4 GHz** network. ESP32 does not support 5 GHz |
| `WiFi.status()` returns `WL_NO_SSID_AVAIL` | Network out of range or hidden | Move closer to router; if hidden SSID, configure accordingly |
| Works at home but not at university | Captive portal / WPA2-Enterprise | University WiFi often requires special config. Use a mobile hotspot for testing |

### Firebase Authentication Failed

| Symptom | Cause | Fix |
|---------|-------|-----|
| `INVALID_API_KEY` error | Wrong API key | Copy `apiKey` from Firebase Console → Project Settings |
| `EMAIL_NOT_FOUND` | User doesn't exist | Create user in Authentication → Users → Add user |
| `INVALID_PASSWORD` | Wrong password | Reset password in Firebase Console |
| `OPERATION_NOT_ALLOWED` | Email auth not enabled | Enable Email/Password in Authentication → Sign-in method |

### No Data Appearing in Dashboard

| Symptom | Cause | Fix |
|---------|-------|-----|
| Dashboard loads but shows no data | Database URL mismatch | Ensure `databaseURL` in `firebase-config.js` matches exactly |
| Console shows CORS error | Using `file://` protocol | Serve with a local HTTP server (see Option A) |
| Console shows permission denied | Rules expired or wrong | Re-apply test mode rules or update `database.rules.json` |
| Data appears in console but not dashboard | Wrong database path | Verify dashboard listens to `SmartStudySpace/` path |

### ESP32 Crashes or Restarts

| Symptom | Cause | Fix |
|---------|-------|-----|
| Brownout detector triggered | Insufficient USB power | Use a powered USB hub or dedicated 5V supply |
| Stack overflow / Guru Meditation | Too many Firebase writes | Increase `FIREBASE_UPDATE_INTERVAL` (e.g., 2000ms) |
| WDT reset | Blocking code in loop | Ensure `delay()` or `yield()` exists in loop |

### Token / Time Sync Errors

| Symptom | Cause | Fix |
|---------|-------|-----|
| `TOKEN_ERROR` or expired token | System time not set | Ensure NTP sync is working: `configTime(0, 0, NTP_SERVER)` |
| Token refresh fails | No internet after initial connect | Check WiFi stability; add reconnection logic |
| `-4` or `-7` error codes | Firebase SSL handshake fails | Verify `DATABASE_URL` starts with `https://` |

> [!NOTE]
> For detailed Firebase ESP Client error codes, see the [library documentation](https://github.com/mobizt/Firebase-ESP-Client).

---

## Quick Reference Card

```
╔══════════════════════════════════════════════════════╗
║         SMART STUDY SPACE — QUICK REFERENCE          ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║  Firebase Console:                                   ║
║    https://console.firebase.google.com               ║
║                                                      ║
║  Database URL:                                       ║
║    https://<project-id>-default-rtdb.firebaseio.com  ║
║                                                      ║
║  Database Path:      SmartStudySpace/                ║
║  Board:              ESP32 Dev Module                ║
║  Baud Rate:          115200                          ║
║  Firebase Library:   Firebase ESP Client (Mobizt)    ║
║  Library Version:    4.4.x                           ║
║  NTP Server:         pool.ntp.org                    ║
║  Update Interval:    1000ms                          ║
║                                                      ║
╚══════════════════════════════════════════════════════╝
```
