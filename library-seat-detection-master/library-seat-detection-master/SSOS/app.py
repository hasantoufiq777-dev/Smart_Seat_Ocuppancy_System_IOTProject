import os
# Prevent low-level PyTorch / OpenBLAS threading segmentation faults on ARM64 / Raspberry Pi 5
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
os.environ['VECLIB_MAXIMUM_THREADS'] = '1'
os.environ['NUMEXPR_NUM_THREADS'] = '1'

import atexit
import sys
import cv2
import numpy as np
import threading
import queue
import time
from datetime import datetime


import config
from detector import SeatDetector
from logger import SeatLogger

# --- Flexible Camera Wrapper to support both USB webcams (OpenCV) and Pi Cam (Picamera2) ---
class CameraStream:
    def __init__(self, width=640, height=480):
        self.use_picamera = False
        self.cap = None
        self.picam = None
        self.active_source = "None"
        self.width = width
        self.height = height
        self._released = False

        # Picamera2 only exists on Raspberry Pi — skip entirely on Windows/macOS
        # to avoid import side-effects and wasted init time.
        if sys.platform.startswith("linux"):
            self._try_picamera2(width, height)

        if not self.use_picamera:
            self._open_opencv_camera(width, height)

        # Guarantee the device is released even if the process crashes mid-run
        atexit.register(self.release)

    def _try_picamera2(self, width, height):
        try:
            print("[Camera] Attempting to import Picamera2...")
            from picamera2 import Picamera2
            from libcamera import controls

            print("[Camera] Picamera2 imported successfully. Initializing Pi Camera...")
            self.picam = Picamera2()
            config_preview = self.picam.create_preview_configuration(main={"size": (width, height)})
            self.picam.configure(config_preview)
            self.picam.start()

            time.sleep(1.0)

            try:
                self.picam.set_controls({"AfMode": controls.AfModeEnum.Continuous})
                print("[Camera] Continuous Autofocus (CAF) enabled successfully.")
            except Exception as af_err:
                print(f"[Camera] Could not enable Autofocus (camera might not support AF controls): {af_err}")

            self.use_picamera = True
            self.active_source = "Picamera2"
            print("[Camera] Native Pi Camera initialized successfully via Picamera2.")
        except Exception as e:
            print(f"[Camera] Picamera2 initialization failed/skipped: {e}")
            print("[Camera] Falling back to OpenCV VideoCapture...")
            self.use_picamera = False
            self.picam = None

    def _backend_candidates(self):
        """Platform-safe OpenCV backends. Never use V4L2 on Windows (crashes webcam drivers)."""
        if sys.platform.startswith("win"):
            # DirectShow is the stable Windows path; MSMF as secondary
            return [cv2.CAP_DSHOW, cv2.CAP_MSMF, None]
        if sys.platform.startswith("linux"):
            return [cv2.CAP_V4L2, None]
        # macOS / other
        return [cv2.CAP_AVFOUNDATION if hasattr(cv2, "CAP_AVFOUNDATION") else None, None]

    def _index_candidates(self):
        """Prefer configured index only — avoid hammering indices 0-3 (Windows driver crash)."""
        indices = [config.CAMERA_INDEX]
        if config.CAMERA_INDEX != 0:
            indices.append(0)
        return indices

    def _try_open(self, source, backend, width, height):
        """Open one camera once, configure props, verify a real frame. Release on failure."""
        label = f"index={source}" + (f" backend={backend}" if backend is not None else " backend=default")
        print(f"[Camera] Trying {label}...")

        try:
            if backend is not None:
                cap = cv2.VideoCapture(source, backend)
            else:
                cap = cv2.VideoCapture(source)
        except Exception as e:
            print(f"[Camera] Open failed ({label}): {e}")
            return None

        if not cap.isOpened():
            cap.release()
            return None

        # Configure before first read — fewer renegotiations with the driver
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass

        # Warm-up: discard a couple of frames so exposure/auto-gain settles
        ret, test_frame = False, None
        for _ in range(5):
            ret, test_frame = cap.read()
            if ret and test_frame is not None and test_frame.size > 0:
                break
            time.sleep(0.05)

        if not (ret and test_frame is not None and test_frame.size > 0):
            print(f"[Camera] Opened but no frames ({label}). Releasing.")
            cap.release()
            return None

        return cap

    def _open_opencv_camera(self, width, height):
        print("[Camera] Opening webcam via OpenCV (platform-safe backends)...")
        for source in self._index_candidates():
            if isinstance(source, int) and source < 0:
                continue
            for backend in self._backend_candidates():
                cap = self._try_open(source, backend, width, height)
                if cap is not None:
                    self.cap = cap
                    self.active_source = str(source)
                    self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or width
                    self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or height
                    backend_name = backend if backend is not None else "default"
                    print(f"[Camera] Success! OpenCV camera index={source} backend={backend_name} "
                          f"({self.width}x{self.height})")
                    return
        print("[Camera] All OpenCV open attempts failed.")

    def read(self):
        if self.use_picamera:
            try:
                frame = self.picam.capture_array()
                # Picamera2 returns RGB, OpenCV GUI expects BGR
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                return True, frame
            except Exception as e:
                print(f"[Camera Read Error] {e}")
                return False, None
        else:
            if self.cap is not None and self.cap.isOpened():
                return self.cap.read()
            return False, None

    def isOpened(self):
        if self.use_picamera:
            return self.picam is not None
        return self.cap is not None and self.cap.isOpened()

    def get_resolution(self):
        if self.use_picamera:
            return self.width, self.height
        else:
            if self.cap is not None:
                w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                # Fallback if properties return 0
                if w == 0 or h == 0:
                    return self.width, self.height
                return w, h
            return 640, 480

    def get(self, prop):
        if self.use_picamera:
            if prop in (cv2.CAP_PROP_FRAME_WIDTH, 3):
                return float(self.width)
            elif prop in (cv2.CAP_PROP_FRAME_HEIGHT, 4):
                return float(self.height)
            elif prop in (cv2.CAP_PROP_FPS, 5):
                return float(config.TARGET_FPS)
            return 0.0
        else:
            if self.cap is not None:
                return self.cap.get(prop)
            return 0.0

    def set(self, prop, value):
        if self.use_picamera:
            if prop in (cv2.CAP_PROP_FRAME_WIDTH, 3):
                self.width = int(value)
                return True
            elif prop in (cv2.CAP_PROP_FRAME_HEIGHT, 4):
                self.height = int(value)
                return True
            return False
        else:
            if self.cap is not None:
                return self.cap.set(prop, value)
            return False

    def release(self):
        if self._released:
            return
        self._released = True
        if self.use_picamera and self.picam is not None:
            try:
                self.picam.stop()
                self.picam.close()
                print("[Camera] Released Pi Camera.")
            except Exception:
                pass
            self.picam = None
        else:
            if self.cap is not None:
                try:
                    self.cap.release()
                    print("[Camera] Released OpenCV Camera.")
                except Exception:
                    pass
                self.cap = None


# --- Asynchronous Worker Thread for Detection ---
class DetectionWorker(threading.Thread):
    def __init__(self, detector):
        super().__init__()
        self.detector = detector
        self.input_queue = queue.Queue(maxsize=1)
        self.output_queue = queue.Queue()
        self.running = True
        self.daemon = True
        
    def run(self):
        while self.running:
            try:
                # Retrieve frame, wait if empty
                frame = self.input_queue.get(timeout=0.1)
                if frame is None:
                    break
                
                # Perform person detection, face detection, and apparent gender analysis
                results = self.detector.process_frame(frame)
                
                # Push results and the frame to output queue (clear older unconsumed results first)
                while not self.output_queue.empty():
                    try:
                        self.output_queue.get_nowait()
                    except queue.Empty:
                        break
                        
                self.output_queue.put((results, frame))
                self.input_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[Worker Thread Error] {e}")
                
    def submit_frame(self, frame):
        """Submit a frame to be processed. If the worker is busy, drop the frame to prevent lag."""
        if self.input_queue.full():
            try:
                self.input_queue.get_nowait()
            except queue.Empty:
                pass
        self.input_queue.put(frame.copy())
        
    def get_results(self):
        """Returns the latest detection results and processed frame if available, otherwise (None, None)."""
        if not self.output_queue.empty():
            return self.output_queue.get()
        return None, None


    def stop(self):
        self.running = False
        self.input_queue.put(None)


# --- Helper GUI Drawing Functions for Premium HUD ---
def draw_semi_transparent_rect(img, pt1, pt2, color, alpha=0.6):
    """Draws a semi-transparent filled rectangle for HUD panels."""
    overlay = img.copy()
    cv2.rectangle(overlay, pt1, pt2, color, -1)
    cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)

def draw_corners(img, box, color, thickness=2, length=15):
    """Draws advanced target bracket corners around a bounding box."""
    x1, y1, x2, y2 = box
    t_thick = thickness * 2
    # Top-left corner
    cv2.line(img, (x1, y1), (x1 + length, y1), color, t_thick)
    cv2.line(img, (x1, y1), (x1, y1 + length), color, t_thick)
    # Top-right corner
    cv2.line(img, (x2, y1), (x2 - length, y1), color, t_thick)
    cv2.line(img, (x2, y1), (x2, y1 + length), color, t_thick)
    # Bottom-left corner
    cv2.line(img, (x1, y2), (x1 + length, y2), color, t_thick)
    cv2.line(img, (x1, y2), (x1, y2 - length), color, t_thick)
    # Bottom-right corner
    cv2.line(img, (x2, y2), (x2 - length, y2), color, t_thick)
    cv2.line(img, (x2, y2), (x2, y2 - length), color, t_thick)
    
    # Outer thin boundary box
    cv2.rectangle(img, (x1, y1), (x2, y2), color, 1, cv2.LINE_AA)


def draw_centered_text(img, text, font, scale, color, thickness, y_pos):
    """Draws text centered horizontally on the frame."""
    size = cv2.getTextSize(text, font, scale, thickness)[0]
    x_pos = (img.shape[1] - size[0]) // 2
    cv2.putText(img, text, (x_pos, y_pos), font, scale, color, thickness, cv2.LINE_AA)


# --- Main Application Loop ---
def main():
    # 1. Initialize Window & Show Loading Screen
    window_name = "Seat Tracker - Apparent Gender Estimation"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    
    # Create loading screen with configuration resolution
    width = config.FRAME_WIDTH
    height = config.FRAME_HEIGHT
    loading_frame = np.zeros((height, width, 3), dtype=np.uint8)
    
    # Calculate screen center coordinates for dynamic centering
    cx = width // 2
    cy = height // 2
    
    # Draw loading UI (dynamic and centered)
    draw_centered_text(loading_frame, "Apparent Gender Seat Tracker", cv2.FONT_HERSHEY_SIMPLEX, 0.85, (255, 255, 255), 2, cy - 60)
    draw_centered_text(loading_frame, "SYSTEM INITIALIZATION", cv2.FONT_HERSHEY_SIMPLEX, 0.45, config.COLOR_SEAT_1, 1, cy - 25)
    draw_centered_text(loading_frame, "Loading weights & compiling models...", cv2.FONT_HERSHEY_SIMPLEX, 0.5, (160, 160, 160), 1, cy + 40)
    draw_centered_text(loading_frame, "Please wait, first startup might take a minute...", cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120, 120, 120), 1, cy + 65)
    
    # Progress bar background
    cv2.rectangle(loading_frame, (cx - 170, cy + 100), (cx + 170, cy + 115), (60, 60, 60), -1)
    cv2.imshow(window_name, loading_frame)
    cv2.waitKey(100) # Force OpenCV to render the frame
    
    # Initialize Detector
    detector = SeatDetector()
    
    # Fill progress bar to 50%
    cv2.rectangle(loading_frame, (cx - 168, cy + 102), (cx, cy + 113), config.COLOR_SEAT_1, -1)
    cv2.imshow(window_name, loading_frame)
    cv2.waitKey(100)
    
    # Warmup models (runs dummy inference to cache weights)
    detector.warmup()
    
    # Fill progress bar to 100%
    cv2.rectangle(loading_frame, (cx - 168, cy + 102), (cx + 168, cy + 113), config.COLOR_SUCCESS, -1)
    draw_centered_text(loading_frame, "Initialization Complete! Opening Camera...", cv2.FONT_HERSHEY_SIMPLEX, 0.5, config.COLOR_SUCCESS, 1, cy + 155)
    cv2.imshow(window_name, loading_frame)
    cv2.waitKey(1000)

    
    # 2. Camera Setup & Connection (Flexible Camera Wrapper)
    cap = CameraStream(config.FRAME_WIDTH, config.FRAME_HEIGHT)
    worker = None
    logger = None

    try:
        if not cap.isOpened():
            print("[Error] No working camera stream (Picamera2 or OpenCV) found. Exiting application.")
            return

        active_idx = cap.active_source

        # Get actual camera resolution
        width, height = cap.get_resolution()
        print(f"[System] Active Resolution: {width}x{height} | Unlimited multi-person tracking")

        # 3. Initialize Logger & Asynchronous Worker Thread
        logger = SeatLogger()
        worker = DetectionWorker(detector)
        worker.start()

        # Dynamic state keyed by persistent track_id (unlimited people)
        latest_detections = {}  # track_id -> detection dict
        stable_state = {}       # track_id -> {occupied, gender}
        candidate_state = {}    # track_id -> {occupied, gender}
        consecutive_frames = {} # track_id -> int
        display_slots = {}      # track_id -> left-to-right slot (1-based)

        # List of recent event logs to display in HUD (up to 3 items)
        recent_logs = []

        # Frame time variables to display actual FPS
        prev_time = time.time()
        fps = 0.0
        _summary_push_counter = 0

        print("\n==============================================")
        print("  Apparent Gender Seat Tracker is now RUNNING")
        print("  Multi-person: all faces in frame are tracked")
        print("  Controls:")
        print("    - Press 'q' or 'ESC' in the window to QUIT.")
        print("    - Press 'c' to CLEAR the log file and stats.")
        print("==============================================\n")

        # Initialize display frame as a black frame on startup to prevent None errors
        display_frame = np.zeros((height, width, 3), dtype=np.uint8)

        while True:
        # 4. Capture Frame
            ret, frame = cap.read()
            if not ret:
                print("[Camera Error] Failed to read frame from webcam.")
                break

            # 5. Submit frame to worker thread (non-blocking)
            worker.submit_frame(frame)

            # 6. Retrieve results and the corresponding processed frame
            results, processed_frame = worker.get_results()

            # If we got a new processed frame, update display_frame and state machine
            if results is not None and processed_frame is not None:
                active_ids = set()
                display_slots = {}

                # Faces are already left→right sorted; assign display slots 1..N
                for slot, face in enumerate(results, start=1):
                    tid = face["track_id"]
                    active_ids.add(tid)
                    display_slots[tid] = slot

                    gender = face["gender"]
                    conf = face["confidence"]
                    prev = latest_detections.get(tid, {})
                    if gender == "Unknown" and stable_state.get(tid, {}).get("gender") in ("Male", "Female"):
                        gender = stable_state[tid]["gender"]
                        conf = prev.get("confidence", conf)

                    latest_detections[tid] = {
                        "occupied": True,
                        "gender": gender,
                        "confidence": conf,
                        "person_box": face["box"],
                        "face_box": face["box"],
                        "display_slot": slot,
                    }

                # Mark people who disappeared this frame as unoccupied (EXIT path)
                for tid in list(stable_state.keys()):
                    if tid not in active_ids:
                        latest_detections[tid] = {
                            "occupied": False,
                            "gender": "Unknown",
                            "confidence": 0.0,
                            "person_box": None,
                            "face_box": None,
                            "display_slot": display_slots.get(tid),
                        }

                # Ensure state dicts exist for every active / pending id
                for tid in set(latest_detections.keys()) | set(stable_state.keys()):
                    if tid not in stable_state:
                        stable_state[tid] = {"occupied": False, "gender": "Unknown"}
                    if tid not in candidate_state:
                        candidate_state[tid] = {"occupied": False, "gender": "Unknown"}
                    if tid not in consecutive_frames:
                        consecutive_frames[tid] = 0

                display_frame = processed_frame.copy()

                # --- State Machine & Stability Filters (per track) ---
                for tid in list(latest_detections.keys()):
                    det = latest_detections[tid]
                    det_occupied = det["occupied"]
                    det_gender = det["gender"]

                    if det_occupied and det_gender == "Unknown" and stable_state[tid]["gender"] in ("Male", "Female"):
                        det_gender = stable_state[tid]["gender"]

                    occ_changed = det_occupied != stable_state[tid]["occupied"]
                    gender_changed = (
                        det_occupied
                        and stable_state[tid]["occupied"]
                        and det_gender != stable_state[tid]["gender"]
                        and det_gender in ("Male", "Female")
                        and stable_state[tid]["gender"] in ("Male", "Female", "Unknown")
                    )

                    if occ_changed or gender_changed:
                        if (det_occupied == candidate_state[tid]["occupied"]) and (det_gender == candidate_state[tid]["gender"]):
                            consecutive_frames[tid] += 1
                        else:
                            candidate_state[tid] = {"occupied": det_occupied, "gender": det_gender}
                            consecutive_frames[tid] = 1

                        needed = config.STABILITY_THRESHOLD_FRAMES
                        if gender_changed and not occ_changed:
                            if stable_state[tid]["gender"] in ("Male", "Female"):
                                needed = config.GENDER_CHANGE_THRESHOLD_FRAMES
                            else:
                                needed = max(config.STABILITY_THRESHOLD_FRAMES, config.GENDER_VOTE_WINDOW // 3)

                        if consecutive_frames[tid] >= needed:
                            old_occupied = stable_state[tid]["occupied"]
                            old_gender = stable_state[tid]["gender"]

                            stable_state[tid] = {"occupied": det_occupied, "gender": det_gender}
                            consecutive_frames[tid] = 0

                            event_type = None
                            log_gender = det_gender

                            if not old_occupied and det_occupied:
                                event_type = "ENTER"
                            elif old_occupied and not det_occupied:
                                event_type = "EXIT"
                                log_gender = old_gender
                            elif (
                                old_occupied and det_occupied
                                and old_gender in ("Male", "Female")
                                and det_gender in ("Male", "Female")
                                and old_gender != det_gender
                            ):
                                event_type = "GENDER_CHANGE"

                            if event_type:
                                slot = det.get("display_slot") or display_slots.get(tid)
                                logger.log_event(
                                    tid, event_type, log_gender, det["confidence"],
                                    display_slot=slot,
                                )

                                time_str = datetime.now().strftime("%H:%M:%S")
                                log_msg = f"[{time_str}] P{tid} {event_type} {log_gender}"
                                recent_logs.append(log_msg)
                                if len(recent_logs) > 3:
                                    recent_logs.pop(0)
                    else:
                        consecutive_frames[tid] = 0
                        candidate_state[tid] = {
                            "occupied": stable_state[tid]["occupied"],
                            "gender": stable_state[tid]["gender"],
                        }

                # Drop tracks that fully exited (keeps dicts from growing forever)
                for tid in list(stable_state.keys()):
                    if (
                        not stable_state[tid]["occupied"]
                        and tid not in active_ids
                        and consecutive_frames.get(tid, 0) == 0
                    ):
                        latest_detections.pop(tid, None)
                        stable_state.pop(tid, None)
                        candidate_state.pop(tid, None)
                        consecutive_frames.pop(tid, None)

                # Periodic live summary to Firebase
                _summary_push_counter += 1
                if _summary_push_counter >= 15:
                    _summary_push_counter = 0
                    live_male = live_female = live_unknown = 0
                    for tid in active_ids:
                        g = stable_state.get(tid, {}).get("gender", "Unknown")
                        if g == "Unknown":
                            g = latest_detections.get(tid, {}).get("gender", "Unknown")
                        if g == "Male":
                            live_male += 1
                        elif g == "Female":
                            live_female += 1
                        else:
                            live_unknown += 1
                    logger.firebase.update_live_summary(
                        len(active_ids), live_male, live_female, live_unknown
                    )

                # Calculate current display FPS based on processed frame rate
                curr_time = time.time()
                fps = 0.9 * fps + 0.1 * (1.0 / (curr_time - prev_time + 1e-6))
                prev_time = curr_time

            # 7. Render Premium HUD GUI overlays

            # A. Draw overlays on every detected face
            active_draw = [
                (tid, det) for tid, det in latest_detections.items()
                if det.get("occupied") and det.get("face_box") is not None
            ]
            # Stable draw order: left → right by face center
            active_draw.sort(key=lambda item: (item[1]["face_box"][0] + item[1]["face_box"][2]) / 2.0)

            for tid, det in active_draw:
                fx1, fy1, fx2, fy2 = det["face_box"]
                palette = config.PERSON_COLORS
                color = palette[(tid - 1) % len(palette)]

                draw_corners(display_frame, (fx1, fy1, fx2, fy2), color, thickness=config.UI_LINE_THICKNESS, length=12)

                fcx = (fx1 + fx2) // 2
                fcy = (fy1 + fy2) // 2
                cv2.line(display_frame, (fcx - 5, fcy), (fcx + 5, fcy), config.COLOR_TEXT_WHITE, 1)
                cv2.line(display_frame, (fcx, fcy - 5), (fcx, fcy + 5), config.COLOR_TEXT_WHITE, 1)

                gender = stable_state.get(tid, {}).get("gender", "Unknown")
                if gender == "Unknown":
                    gender = det["gender"]
                conf = det["confidence"]
                slot = det.get("display_slot") or display_slots.get(tid, "?")
                label = (
                    f"P{tid} #{slot}: {gender} ({conf:.0f}%)"
                    if gender != "Unknown"
                    else f"P{tid} #{slot}: Analyzing..."
                )

                (tw, th), baseline = cv2.getTextSize(label, config.UI_FONT, config.UI_FONT_SCALE_MD, 1)
                cv2.rectangle(display_frame, (fx1, fy1 - th - 12), (fx1 + tw + 10, fy1), color, -1)
                cv2.putText(display_frame, label, (fx1 + 6, fy1 - 5), config.UI_FONT, config.UI_FONT_SCALE_MD, (10, 10, 10), 1, cv2.LINE_AA)
                cv2.putText(display_frame, label, (fx1 + 5, fy1 - 6), config.UI_FONT, config.UI_FONT_SCALE_MD, config.COLOR_TEXT_WHITE, 1, cv2.LINE_AA)

            # C. HUD summary panel (top-left) — scales with person count
            people_now = len(active_draw)
            live_male = live_female = live_unknown = 0
            for tid, det in active_draw:
                g = stable_state.get(tid, {}).get("gender", "Unknown")
                if g == "Unknown":
                    g = det.get("gender", "Unknown")
                if g == "Male":
                    live_male += 1
                elif g == "Female":
                    live_female += 1
                else:
                    live_unknown += 1

            totals = logger.get_totals()
            # Show up to 8 person lines in the roster; extra people only in the count
            roster_limit = 8
            roster_lines = min(people_now, roster_limit)
            card_w = 280
            card_h = 78 + roster_lines * 16
            margin = 15

            draw_semi_transparent_rect(display_frame, (margin, margin), (margin + card_w, margin + card_h), config.COLOR_BG_CARD, alpha=0.6)
            cv2.rectangle(display_frame, (margin, margin), (margin + card_w, margin + card_h), config.COLOR_SEAT_1, 1, cv2.LINE_AA)

            cv2.putText(
                display_frame, f"PEOPLE IN FRAME: {people_now}",
                (margin + 10, margin + 22), config.UI_FONT, config.UI_FONT_SCALE_MD,
                config.COLOR_SEAT_1, 1, cv2.LINE_AA,
            )
            cv2.putText(
                display_frame,
                f"Live  M:{live_male}  F:{live_female}  ?:{live_unknown}",
                (margin + 10, margin + 42), config.UI_FONT, config.UI_FONT_SCALE_SM,
                config.COLOR_TEXT_WHITE, 1, cv2.LINE_AA,
            )
            cv2.putText(
                display_frame,
                f"Session ENTER M:{totals['Male']} F:{totals['Female']}",
                (margin + 10, margin + 58), config.UI_FONT, config.UI_FONT_SCALE_SM,
                config.COLOR_TEXT_MUTED, 1, cv2.LINE_AA,
            )

            for i, (tid, det) in enumerate(active_draw[:roster_limit]):
                g = stable_state.get(tid, {}).get("gender", "Unknown")
                if g == "Unknown":
                    g = det.get("gender", "Unknown")
                conf = det.get("confidence", 0.0)
                line = f"P{tid}: {g} ({conf:.0f}%)"
                y = margin + 76 + i * 16
                col = config.PERSON_COLORS[(tid - 1) % len(config.PERSON_COLORS)]
                cv2.putText(display_frame, line, (margin + 10, y), config.UI_FONT, config.UI_FONT_SCALE_SM, col, 1, cv2.LINE_AA)

            if people_now > roster_limit:
                cv2.putText(
                    display_frame, f"+{people_now - roster_limit} more...",
                    (margin + 10, margin + 76 + roster_limit * 16),
                    config.UI_FONT, config.UI_FONT_SCALE_SM, config.COLOR_TEXT_MUTED, 1, cv2.LINE_AA,
                )

            # D. Controls Panel & Live Ticker (Bottom of Screen)
            ticker_h = 90
            draw_semi_transparent_rect(display_frame, (margin, height - margin - ticker_h), (width - margin, height - margin), config.COLOR_BG_CARD, alpha=0.5)
            cv2.rectangle(display_frame, (margin, height - margin - ticker_h), (width - margin, height - margin), (80, 80, 80), 1, cv2.LINE_AA)

            b_y = height - margin - ticker_h
            cv2.putText(display_frame, f"SYSTEM CONTROLS (Cam: {active_idx} | FPS: {fps:.1f} | People: {people_now})", (margin + 15, b_y + 20), config.UI_FONT, config.UI_FONT_SCALE_SM, config.COLOR_SEAT_1, 1, cv2.LINE_AA)
            cv2.putText(display_frame, "[Q] Quit Application", (margin + 15, b_y + 42), config.UI_FONT, config.UI_FONT_SCALE_SM, config.COLOR_TEXT_WHITE, 1, cv2.LINE_AA)
            cv2.putText(display_frame, "[C] Clear CSV Log & Counters", (margin + 15, b_y + 64), config.UI_FONT, config.UI_FONT_SCALE_SM, config.COLOR_TEXT_WHITE, 1, cv2.LINE_AA)

            ticker_x = width // 2 - 20
            cv2.putText(display_frame, "LIVE STATE-CHANGE TRANSITIONS LOG", (ticker_x, b_y + 20), config.UI_FONT, config.UI_FONT_SCALE_SM, config.COLOR_DIVIDER, 1, cv2.LINE_AA)

            if not recent_logs:
                cv2.putText(display_frame, "Waiting for occupancy state changes...", (ticker_x, b_y + 45), config.UI_FONT, config.UI_FONT_SCALE_SM, config.COLOR_TEXT_MUTED, 1, cv2.LINE_AA)
            else:
                for idx, log_msg in enumerate(recent_logs):
                    text_color = config.COLOR_TEXT_WHITE if idx == len(recent_logs) - 1 else config.COLOR_TEXT_MUTED
                    cv2.putText(display_frame, log_msg, (ticker_x, b_y + 42 + idx * 18), config.UI_FONT, config.UI_FONT_SCALE_SM, text_color, 1, cv2.LINE_AA)

            # 8. Show frame
            cv2.imshow(window_name, display_frame)

            # 9. Key Press Handling
            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), ord('Q'), 27): # q, Q or ESC
                print("[System] Quit command detected.")
                break
            elif key in (ord('c'), ord('C')):
                print("[System] Clearing logs...")
                logger.clear_logs()
                # Clear ticker
                recent_logs.clear()
                latest_detections.clear()
                stable_state.clear()
                candidate_state.clear()
                consecutive_frames.clear()
                display_slots.clear()
    finally:
        # Cleanup — always release camera so Windows webcam drivers stay healthy
        print("[System] Cleaning up...")
        if worker is not None:
            print("[System] Stopping worker thread...")
            worker.stop()
            worker.join(timeout=1.0)
        if logger is not None:
            print("[System] Stopping Firebase uploader...")
            logger.stop()
        print("[System] Releasing camera...")
        cap.release()
        cv2.destroyAllWindows()
        print("[System] Exited successfully.")

if __name__ == "__main__":
    main()
