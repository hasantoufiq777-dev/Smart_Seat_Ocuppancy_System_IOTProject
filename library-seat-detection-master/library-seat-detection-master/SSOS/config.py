import cv2

# Camera Settings
CAMERA_INDEX = 0             # Default camera index
FRAME_WIDTH = 1280           # Capture width (HD 720p)
FRAME_HEIGHT = 720           # Capture height (HD 720p)
TARGET_FPS = 60              # Target display frame rate (smoother capture)


# Soft cap on simultaneous faces (None = no limit beyond what the face detector returns)
MAX_PERSONS = None

# Model Configurations (OpenCV DNN models)
import os
_base_dir = os.path.dirname(os.path.abspath(__file__))
FACE_PROTO = os.path.join(_base_dir, "weights", "deploy.prototxt.txt")
FACE_MODEL = os.path.join(_base_dir, "weights", "res10_300x300_ssd_iter_140000_fp16.caffemodel")
GENDER_PROTO = os.path.join(_base_dir, "weights", "deploy_gender.prototxt")
GENDER_MODEL = os.path.join(_base_dir, "weights", "gender_net.caffemodel")



# Preprocessing Mean Values (BGR mean subtraction for genderNet)
MODEL_MEAN_VALUES = (78.4263377603, 87.7689143744, 114.895847746)
GENDER_LIST = ['Male', 'Female']

# Detection thresholds — higher = fewer false / flickering labels
FACE_CONFIDENCE_THRESHOLD = 0.40    # SSD face score (0.0–1.0)
GENDER_CONFIDENCE_THRESHOLD = 0.50  # Min softmax probability to accept Male/Female
GENDER_SCORE_MARGIN = 0.05         # Min gap between top-2 gender scores
FACE_PAD_RATIO = 0.45               # Expand face crop (genderNet likes context)
MIN_FACE_SIZE = 20                  # Ignore tiny faces (pixels)

# Temporal gender smoothing (majority vote per tracked face)
GENDER_VOTE_WINDOW = 8              # Frames kept in vote history
GENDER_VOTE_MIN_AGREE = 0.51        # Fraction of votes that must agree to lock/flip
GENDER_TRACK_MAX_DIST = 120         # Max L1 center distance to match same face
GENDER_TRACK_TTL = 20               # Drop track after this many unseen frames

# State Stability Settings
# Occupancy must persist this many processed frames before ENTER/EXIT logs.
STABILITY_THRESHOLD_FRAMES = 8
# Gender flips need longer agreement — stops rapid Male↔Female flicker in logs/HUD.
GENDER_CHANGE_THRESHOLD_FRAMES = 10

# Logging Configurations
LOG_FILE_PATH = "seat_log.csv"

# UI & Styling Design System (Colors are in BGR format for OpenCV)
COLOR_SEAT_1 = (235, 175, 50)     # Neon Cyan/Blue-ish
COLOR_SEAT_2 = (200, 50, 250)     # Neon Pink/Magenta-ish
COLOR_DIVIDER = (80, 240, 80)     # Neon Green
COLOR_BG_CARD = (30, 30, 30)      # Sleek Dark Gray for overlays
COLOR_TEXT_WHITE = (255, 255, 255) # Pure White text
COLOR_TEXT_MUTED = (180, 180, 180) # Muted Gray text
COLOR_SUCCESS = (80, 240, 80)     # Success/Detected Green
COLOR_ALERT = (50, 50, 240)       # Red-ish Alert
# Rotating palette for unlimited person overlays (BGR)
PERSON_COLORS = [
    (235, 175, 50),
    (200, 50, 250),
    (80, 240, 80),
    (50, 200, 255),
    (80, 80, 255),
    (255, 180, 50),
    (255, 100, 180),
    (100, 255, 200),
]

UI_FONT = cv2.FONT_HERSHEY_SIMPLEX
UI_FONT_SCALE_LG = 0.7
UI_FONT_SCALE_MD = 0.5
UI_FONT_SCALE_SM = 0.4
UI_LINE_THICKNESS = 2

# ── Firebase Realtime Database Configuration ──────────────────
# Uses the same project as the ESP32. The Pi pushes gender data
# to /SmartStudySpace/Seats/SeatX alongside the ESP32 sensor data.
FIREBASE_ENABLED = True
FIREBASE_DATABASE_URL = "https://smartstudyspace-library-default-rtdb.asia-southeast1.firebasedatabase.app"
FIREBASE_DATABASE_SECRET = "gj7rL4gQzWYKMZQrr1AExnmAku9ylbFYujVzFOXq"

# Mapping: leftmost faces (by position order) → Firebase physical seat keys
# Extra people beyond this map are still tracked and written under DetectedPeople/
FIREBASE_SEAT_MAP = {1: "Seat1", 2: "Seat2", 3: "Seat3", 4: "Seat4"}

# Maximum number of recent events to keep in the GenderEventLog node
FIREBASE_MAX_EVENT_LOG = 50
