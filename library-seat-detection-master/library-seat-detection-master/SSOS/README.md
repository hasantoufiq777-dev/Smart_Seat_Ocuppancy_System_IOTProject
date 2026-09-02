# Apparent Gender Seat Tracker (OpenCV DNN Version)

A high-performance, lightweight, and real-time computer vision system built for the Raspberry Pi 5 / PC laptops to detect faces, estimate apparent gender, and track seat assignments.

This version uses **OpenCV's built-in Deep Neural Network (DNN) module** with pre-trained Caffe models. It requires **no heavy dependencies** (completely removing YOLO, PyTorch, TensorFlow, Keras, and DeepFace), ensuring 100% stability, tiny disk space usage, and zero segmentation faults on the Raspberry Pi 5.

---

## 🚀 Key Features
- **Buttery Smooth Live Stream**: Uses a multi-threaded architecture. Camera capture and GUI drawing run on the main thread, while OpenCV DNN inference runs asynchronously on a background worker thread.
- **Robust Hardware Compatibility**: Bypasses all ARM64 architecture conflicts by using OpenCV's native C++ inference engine.
- **Stable Seat Assignment**: Horizontally splits the viewport down the center (Seat 1 = Left, Seat 2 = Right) to map occupant locations without complex multi-object trackers.
- **Transition Event Logger**: Logs entry, exit, and apparent gender change events to `seat_log.csv` only after a state remains stable for a consecutive number of frames.
- **Premium HUD Overlay**: Renders glowing neon cards, corners brackets, face targeting crosshairs, and live status logs.

---

## 🛠️ System Architecture

```
                 +-----------------------------------------+
                 |            Main Preview Thread          |
                 |  - Captures camera frames (30 FPS)      |
                 |  - Draws neon HUD cards and boxes       |
                 |  - Renders UI, processes key commands   |
                 +-------------------+-----------------+
                                     |         ^
                       Submits Frame |         | Returns Async Detections
                                     v         |
                 +-------------------+---------+-----------+
                 |            Worker Analysis Thread       |
                 |  - Runs OpenCV DNN face detector (SSD)  |
                 |  - Maps face centers to Seat 1 / 2      |
                 |  - Crops face and runs Gender Caffe Net |
                 +-----------------------------------------+
```

---

## ⚙️ Installation & Requirements

Since we are using OpenCV's native neural network module, the requirements are extremely simple:

```bash
pip install -r requirements.txt
```

*(Note: We pin `opencv-python<5.0.0` because OpenCV 5.x has deprecated Caffe support, whereas OpenCV 4.x has full native support).*

---

## 🖥️ Running the Application

### 1. Download the Caffe Models
Before running the tracker, download the pre-trained SSD face detector and gender classification models by running:

```bash
python download_models.py
```
This will create a `weights/` directory and download the four model files automatically (total download size is ~51 MB).

### 2. Run the Seat Tracker
Launch the application:

```bash
python app.py
```

*Note: If running inside VNC on Raspberry Pi OS (which uses Wayland by default), force the X11 platform plugin to ensure OpenCV's preview window opens successfully:*
```bash
QT_QPA_PLATFORM=xcb python app.py
```

---

## 🎮 Keyboard Controls
- **`Q` or `ESC`**: Quit the application and release camera streams.
- **`C`**: Clear the logged events CSV file (`seat_log.csv`) and reset session statistics.

---

## 📊 Outputs & Logs

Transitions are appended to `seat_log.csv` in the project root:

| Timestamp | Seat | Event | Gender | Confidence |
| :--- | :--- | :--- | :--- | :--- |
| `2026-07-07 20:42:10` | `1` | `ENTER` | `Male` | `98.2%` |
| `2026-07-07 20:42:15` | `2` | `ENTER` | `Female` | `96.4%` |
| `2026-07-07 20:42:40` | `1` | `EXIT` | `Male` | `N/A` |
