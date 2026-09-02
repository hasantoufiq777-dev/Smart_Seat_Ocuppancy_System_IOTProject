# 🎓 Smart Seat Occupancy System (SSOS) — Real-Time IoT & AI Dashboard

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Hardware: ESP32](https://img.shields.io/badge/Hardware-ESP32-red.svg)](https://www.espressif.com/)
[![AI Platform: Raspberry_Pi_5](https://img.shields.io/badge/AI_Platform-Raspberry_Pi_5-C51A4A.svg)](https://www.raspberrypi.com/)
[![Camera: Arducam_IMX519](https://img.shields.io/badge/Camera-Arducam_IMX519-00599C.svg)](https://www.arducam.com/)
[![Cloud: Firebase](https://img.shields.io/badge/Cloud-Firebase_RTDB-FFCA28.svg)](https://firebase.google.com/)

An end-to-end IoT and Computer Vision system for real-time study space management in libraries and smart campuses. The system integrates **Physical Chair Bounding Box Detection**, **Deep Learning Face Detection**, and **CNN Gender Classification** using a Raspberry Pi 5 with an Arducam IMX519 camera, combined with an ESP32 hardware sensor node (weight, human proximity, noise monitoring). Live data is synced via Firebase to a responsive, light-mode glassmorphism web dashboard with Bluetooth speaker audio warnings (`table.mp3`).



---

## 🛠️ Hardware Components

| Component | Description / Specifications |
| :--- | :--- |
| **ESP32 Dev Module** | Main IoT microcontroller handling physical sensor data ingestion and Firebase sync |
| **Raspberry Pi 5** | High-performance AI edge platform running chair, face, and gender inference |
| **Arducam IMX519 Camera** | 16MP Autofocus HD Camera module for Pi 5 (`setup_pi5_imx519.sh` & `test_imx519_focus.py`) |
| **Force Sensitive Resistors (FSR)** | 4x FSR sensors (Analog input: Pins 34, 35, 32, 33) for seat weight detection |
| **Infrared Proximity Sensors (IR)** | 4x IR sensors (Digital input: Pins 27, 18, 19, 14) for human proximity verification |
| **Sound Detection Sensor** | Analog sound sensor (Pin 36 / VP) for noise level monitoring |
| **Physical Active Buzzer** | Alert buzzer (Pin 23) for local sound threshold warnings |
| **Bluetooth Speaker** | Wireless speaker paired to the client host for custom Web Audio (`table.mp3`) alerts |
| **Solderless Breadboard & Jumpers** | Circuit prototyping and pin interconnections |

---

## 🏗️ End-to-End System Architecture

```
                               ┌───────────────────────────────────────────────────────────┐
                               │       Raspberry Pi 5 + Arducam IMX519 (libcamera)         │
                               │  - Chair Detection (library-seat-detection-master)        │
                               │  - Face Detection (Single Shot MultiBox Detector - SSD)   │
                               │  - Gender Classification (Levi & Hassner Caffe CNN)       │
                               └─────────────────────────────┬─────────────────────────────┘
                                                             │ (HTTPS / Firebase SDK)
                                                             ▼
┌──────────────────────────┐                        ┌──────────────────┐                        ┌─────────────────────────┐
│      ESP32 Hardware      │       HTTPS/REST       │ Firebase Cloud   │       WebSockets       │ Client Web Dashboard    │
│ (FSR + IR + Sound Pin 36)├───────────────────────►│ Realtime Database├───────────────────────►│ (HTML/CSS/JS + Audio)   │
└──────────────────────────┘                        └──────────────────┘                        └────────────┬────────────┘
                                                                                                             │ (System Audio)
                                                                                                             ▼
                                                                                                 ┌────────────────────────┐
                                                                                                 │    Bluetooth Speaker   │
                                                                                                 └────────────────────────┘
```

---

## 🧠 Decision Logic & Sensor Truth Tables

### 1. Physical Seat Occupancy Logic (ESP32)
The combination of Weight (FSR Threshold $\ge 500$) and Human Proximity (IR Sensor Active-LOW) determines the exact physical status of each seat:

| FSR Reading | IR Sensor (Active-LOW) | Weight Status | Human Presence | Output Seat State |
| :---: | :---: | :---: | :---: | :---: |
| $< 500$ | Any (`0` or `1`) | No Weight | N/A | **`AVAILABLE`** |
| $\ge 500$ | `LOW (0)` | Weight Present | Yes | **`OCCUPIED`** |
| $\ge 500$ | `HIGH (1)` | Weight Present | No | **`BAG DETECTED`** |

### 2. Sound Level & Temporal Sustain Hold Window
* **Threshold**: Analog value $> 300$ on ESP32 GPIO `36` (VP).
* **3-Second Hold Window**: Once noise spikes past 300, the system sustains the `"Noisy"` status for a minimum of 3 seconds (`now - lastNoiseTime < 3000`). This prevents rapid audio stuttering and unnecessary database writes caused by raw sound wave oscillations.
* **Instant Firebase Sync**: State transitions (Quiet $\leftrightarrow$ Noisy) upload immediately to trigger web alerts, while raw sound level updates are throttled to every 2 seconds.

---

## 👁️ Computer Vision Pipeline (Pi 5 & Caffe Models)

The vision processing engine combines physical chair tracking with multi-stage deep neural networks:

### 1. Chair Bounding Box Detection & Tracking (`library-seat-detection-master`)
* **Chair Bounding Box Detection (`detect_chair_bb.py`, `detect_chairs_new.py`, `object_detector.py`)**:
  * Detects physical chair bounding boxes in the camera view using `object_detector.py` and logs coordinates into CSV manifests (`seat_bb_chair.csv`, `seat_bb_chairs.csv`, `detection_labels.csv`).
* **Seat & Chair Tracking (`seat.py`, `seat_detection.py`, `seat_utils.py`)**:
  * Monitors chair bounding box regions, calculates overlap with detected humans or objects, and tracks seat availability in real time.

### 2. Deep Learning Face Detection Model
* **Architecture**: Single Shot MultiBox Detector (SSD) with a ResNet-10 backbone.
* **Model Files**:
  * `deploy.prototxt.txt` (defines neural network layer architecture).
  * `res10_300x300_ssd_iter_140000_fp16.caffemodel` (pre-trained model weights).
* **Operation**: Scans the camera stream, detects human faces, extracts bounding boxes, and calculates spatial $X$-coordinates to assign the face to the corresponding chair bounding box.

### 3. Deep Learning Gender Classification Model
* **Architecture**: Convolutional Neural Network (CNN) designed by Gil Levi and Tal Hassner, trained on the Adience dataset.
* **Model Files**:
  * `deploy_gender.prototxt` (defines classifier network layers).
  * `gender_net.caffemodel` (pre-trained gender classification weights).
* **Operation**:
  * Crops the detected face region, resizes it to $227 \times 227$ pixels, applies channel mean subtraction, and passes it through the CNN.
  * Outputs two soft probabilities: `Male` vs. `Female`. The class with the higher confidence score is uploaded to Firebase (`/SmartStudySpace/Seats/SeatX/gender`).
* **Exit Event Overrides**: When an occupant leaves a seat (`genderLastEvent = "EXIT"`), the web dashboard automatically clears the active gender pill to `UNKNOWN`.

---

## 💻 Installation & Execution Guide

### Prerequisite Repository Setup
Clone the repository:
```bash
git clone https://github.com/hasantoufiq777-dev/Smart_Seat_Ocuppancy_System_IOTProject.git
cd Smart_Seat_Ocuppancy_System_IOTProject
```

---

### Part 1: Raspberry Pi 5 AI Vision & Chair Detection (`library-seat-detection-master` / `SSOS`)

1. **Configure Arducam IMX519 Camera Driver on Pi 5**:
   ```bash
   cd library-seat-detection-master
   chmod +x setup_pi5_imx519.sh
   ./setup_pi5_imx519.sh
   sudo reboot
   ```
2. **Test Camera Focus**:
   ```bash
   python3 test_imx519_focus.py
   ```
3. **Install Python dependencies**:
   ```bash
   pip install opencv-python numpy firebase-admin
   ```
4. **Run Chair Bounding Box Detection & Gender Inference**:
   ```bash
   # Run Chair Bounding Box Detection & Tracking
   python3 seat_detection.py

   # Or run main vision application module
   cd ../SSOS
   python3 app.py
   ```

---

### Part 2: ESP32 Firmware Node (`espcode`)

1. Open `espcode/espcode.ino` in **Arduino IDE**.
2. Install required board packages and libraries:
   * Board: `ESP32 Dev Module`
   * Library: `Firebase_ESP_Client` by Mobizt
3. Update Wi-Fi and Firebase credentials in `espcode.ino`:
   ```cpp
   #define WIFI_SSID        "Your_WiFi_Name"
   #define WIFI_PASSWORD    "Your_WiFi_Password"
   #define DATABASE_SECRET  "Your_Firebase_Database_Secret"
   ```
4. Upload to ESP32 and open Serial Monitor at `115200` baud.

---

### Part 3: Web Dashboard (Frontend)

The web dashboard is built with responsive HTML5, Light-Mode Glassmorphism Vanilla CSS, and JavaScript ES modules.

#### 1. Running Locally with Python
```bash
cd dashboard
python -m http.server 3000
```
Open **`http://localhost:3000`** in your browser.

#### 2. Running Locally or Globally via `npm serve`
Install `serve` globally using `npm`:
```bash
npm install -g serve
```
Run `serve` on the dashboard folder:
```bash
# Option A: From inside the dashboard folder
cd dashboard
serve -l 3000

# Option B: Run globally from anywhere
serve e:\iot_dashboard\dashboard -l 3000
```

#### 3. Enabling Bluetooth Speaker Audio Warnings
1. Connect your Computer / Laptop to your **Bluetooth Speaker** via system Bluetooth settings.
2. Open **`http://localhost:3000`** in your browser.
3. **Click anywhere on the dashboard once** to grant browser audio context permissions.
4. When room noise exceeds threshold, `table.mp3` will play through your Bluetooth speaker!

---

## 🎨 Dashboard Features

* **Live Visitor Monitor**: Displays total seats, occupied count, available count, dynamic gender pills (`MALE`, `FEMALE`, `UNKNOWN`), SVG icons, and highlighted state backgrounds (Pastel Green for Occupied, Pastel Amber for Bag Detected).
* **Collapsible Admin Panel**: Click the top-right `[👤 Admin]` button to reveal full diagnostic analytics, FSR/IR raw sensor values, session duration timers, sound waveforms, usage bar charts, and live event logs.

---

## 📜 License
This project is licensed under the MIT License — feel free to use and expand upon it for academic and research purposes!
