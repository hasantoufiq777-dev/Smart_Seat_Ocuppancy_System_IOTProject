import os
# Prevent low-level PyTorch / OpenBLAS threading segmentation faults on ARM64 / Raspberry Pi 5
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'

from collections import deque, Counter

import cv2
import numpy as np
import config


class GenderStabilizer:
    """
    Spatially tracks faces across frames and majority-votes gender so
    single-frame flips do not change the reported label.
    Each face gets a persistent track_id for multi-person state machines.
    """

    def __init__(self):
        self.tracks = []  # each: {id, cx, cy, votes: deque, last_seen, ...}
        self._frame_id = 0
        self._next_id = 1
        self.max_match_dist = config.GENDER_TRACK_MAX_DIST
        self.vote_window = config.GENDER_VOTE_WINDOW
        self.min_agree = config.GENDER_VOTE_MIN_AGREE
        self.track_ttl = config.GENDER_TRACK_TTL

    def _match_track(self, cx, cy):
        best_i, best_d = None, self.max_match_dist
        for i, t in enumerate(self.tracks):
            d = abs(t["cx"] - cx) + abs(t["cy"] - cy)
            if d < best_d:
                best_d, best_i = d, i
        return best_i

    def update(self, detections):
        """
        detections: list of dicts with box, gender, confidence (raw).
        Returns same list with gender/confidence replaced by stabilized values
        and a persistent track_id per face.
        """
        self._frame_id += 1
        used = set()
        stabilized = []

        for det in detections:
            x1, y1, x2, y2 = det["box"]
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            idx = self._match_track(cx, cy)

            if idx is None or idx in used:
                track = {
                    "id": self._next_id,
                    "cx": cx,
                    "cy": cy,
                    "votes": deque(maxlen=self.vote_window),
                    "last_seen": self._frame_id,
                    "stable_gender": "Unknown",
                    "stable_conf": 0.0,
                }
                self._next_id += 1
                self.tracks.append(track)
                idx = len(self.tracks) - 1

            used.add(idx)
            track = self.tracks[idx]
            track["cx"] = 0.7 * track["cx"] + 0.3 * cx
            track["cy"] = 0.7 * track["cy"] + 0.3 * cy
            track["last_seen"] = self._frame_id

            raw_gender = det["gender"]
            raw_conf = det["confidence"]

            # Only count confident Male/Female votes; skip Unknown / weak
            if raw_gender in ("Male", "Female") and raw_conf >= config.GENDER_CONFIDENCE_THRESHOLD * 100.0:
                track["votes"].append(raw_gender)

            stable_gender, stable_conf = self._majority(track)
            # Sticky: once we have a stable gender, keep it until a clear majority flips
            if stable_gender == "Unknown" and track["stable_gender"] in ("Male", "Female"):
                stable_gender = track["stable_gender"]
                stable_conf = track["stable_conf"]
            else:
                track["stable_gender"] = stable_gender
                track["stable_conf"] = stable_conf

            stabilized.append({
                "box": det["box"],
                "gender": stable_gender,
                "confidence": stable_conf,
                "raw_gender": raw_gender,
                "raw_confidence": raw_conf,
                "track_id": track["id"],
            })

        # Drop stale tracks
        self.tracks = [
            t for t in self.tracks
            if self._frame_id - t["last_seen"] <= self.track_ttl
        ]
        return stabilized

    def _majority(self, track):
        votes = list(track["votes"])
        if len(votes) < max(3, self.vote_window // 3):
            return "Unknown", 0.0

        counts = Counter(votes)
        label, n = counts.most_common(1)[0]
        agree = n / len(votes)
        if agree < self.min_agree:
            return track.get("stable_gender", "Unknown"), track.get("stable_conf", 0.0)

        conf = agree * 100.0
        return label, conf


class SeatDetector:
    def __init__(self):
        print("[Detector] Initializing OpenCV DNN Caffe models...")

        # Load Caffe face detection network
        self.face_net = cv2.dnn.readNet(config.FACE_PROTO, config.FACE_MODEL)

        # Load Caffe gender classification network
        self.gender_net = cv2.dnn.readNet(config.GENDER_PROTO, config.GENDER_MODEL)
        self.stabilizer = GenderStabilizer()
        print("[Detector] Models loaded successfully.")

    def warmup(self):
        """
        Performs dummy inferences to initialize network layers.
        """
        print("[Detector] Warming up face model...")
        dummy_face = np.zeros((300, 300, 3), dtype=np.uint8)
        blob_face = cv2.dnn.blobFromImage(dummy_face, 1.0, (300, 300), (104.0, 177.0, 123.0))
        self.face_net.setInput(blob_face)
        self.face_net.forward()

        print("[Detector] Warming up gender model...")
        dummy_gender = np.zeros((227, 227, 3), dtype=np.uint8)
        blob_gender = cv2.dnn.blobFromImage(dummy_gender, 1.0, (227, 227), config.MODEL_MEAN_VALUES, swapRB=False)
        self.gender_net.setInput(blob_gender)
        self.gender_net.forward()
        print("[Detector] Warmup complete.")

    @staticmethod
    def _padded_square_crop(frame, x1, y1, x2, y2, pad_ratio):
        """Expand face box and force a square crop — genderNet is more accurate this way."""
        h, w = frame.shape[:2]
        bw = max(1, x2 - x1)
        bh = max(1, y2 - y1)
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        side = max(bw, bh) * (1.0 + pad_ratio)

        nx1 = int(round(cx - side / 2.0))
        ny1 = int(round(cy - side / 2.0))
        nx2 = int(round(cx + side / 2.0))
        ny2 = int(round(cy + side / 2.0))

        nx1, ny1 = max(0, nx1), max(0, ny1)
        nx2, ny2 = min(w, nx2), min(h, ny2)

        if nx2 <= nx1 or ny2 <= ny1:
            return None
        return frame[ny1:ny2, nx1:nx2]

    def _estimate_gender(self, face_crop):
        """
        Run genderNet with confidence + score-margin gating.
        Returns (label, confidence_percent). Unsure → Unknown.
        """
        blob_gender = cv2.dnn.blobFromImage(
            face_crop, 1.0, (227, 227),
            config.MODEL_MEAN_VALUES,
            swapRB=False, crop=False
        )
        self.gender_net.setInput(blob_gender)
        preds = self.gender_net.forward()[0].astype(np.float64)
        # Network already ends in Softmax ("prob"); normalize in case of numeric drift
        total = float(np.sum(preds))
        probs = preds / total if total > 0 else preds

        gender_idx = int(np.argmax(probs))
        top = float(probs[gender_idx])
        second = float(np.partition(probs, -2)[-2]) if len(probs) > 1 else 0.0
        margin = top - second

        if top < config.GENDER_CONFIDENCE_THRESHOLD or margin < config.GENDER_SCORE_MARGIN:
            return "Unknown", top * 100.0

        return config.GENDER_LIST[gender_idx], top * 100.0

    def process_frame(self, frame):
        """
        Runs Caffe face detection on the entire frame, crops each face,
        estimates apparent gender, stabilizes over time, and returns faces
        sorted left-to-right.
        """
        height, width, _ = frame.shape

        # 1. Run Caffe Face Detection
        blob_face = cv2.dnn.blobFromImage(frame, 1.0, (300, 300), (104.0, 177.0, 123.0), swapRB=False)
        self.face_net.setInput(blob_face)
        detections = self.face_net.forward()

        detected_faces = []
        num_detections = detections.shape[2]

        for i in range(num_detections):
            confidence = float(detections[0, 0, i, 2])

            if confidence < config.FACE_CONFIDENCE_THRESHOLD:
                continue

            box = detections[0, 0, i, 3:7] * np.array([width, height, width, height])
            x1, y1, x2, y2 = box.astype("int")

            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(width - 1, x2), min(height - 1, y2)

            if x2 <= x1 or y2 <= y1:
                continue

            face_w, face_h = x2 - x1, y2 - y1
            if face_w < config.MIN_FACE_SIZE or face_h < config.MIN_FACE_SIZE:
                continue

            face_crop = self._padded_square_crop(frame, x1, y1, x2, y2, config.FACE_PAD_RATIO)
            if face_crop is None or face_crop.size == 0:
                continue

            gender_label = "Unknown"
            gender_conf = 0.0
            try:
                gender_label, gender_conf = self._estimate_gender(face_crop)
            except Exception:
                pass

            detected_faces.append({
                "box": (x1, y1, x2, y2),
                "gender": gender_label,
                "confidence": gender_conf,
                "face_score": confidence * 100.0,
            })

        # NMS-ish: drop overlapping boxes (keep higher face score)
        detected_faces = self._suppress_overlaps(detected_faces)

        # 2. Sort left → right, then temporally stabilize gender
        sorted_faces = sorted(
            detected_faces,
            key=lambda f: (f["box"][0] + f["box"][2]) / 2.0
        )
        if config.MAX_PERSONS is not None and config.MAX_PERSONS > 0:
            sorted_faces = sorted_faces[: int(config.MAX_PERSONS)]
        return self.stabilizer.update(sorted_faces)

    @staticmethod
    def _suppress_overlaps(faces, iou_thresh=0.45):
        if len(faces) <= 1:
            return faces

        faces = sorted(faces, key=lambda f: f.get("face_score", f["confidence"]), reverse=True)
        kept = []

        def iou(a, b):
            ax1, ay1, ax2, ay2 = a
            bx1, by1, bx2, by2 = b
            ix1, iy1 = max(ax1, bx1), max(ay1, by1)
            ix2, iy2 = min(ax2, bx2), min(ay2, by2)
            iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
            inter = iw * ih
            if inter <= 0:
                return 0.0
            area_a = max(1, (ax2 - ax1) * (ay2 - ay1))
            area_b = max(1, (bx2 - bx1) * (by2 - by1))
            return inter / float(area_a + area_b - inter)

        for face in faces:
            if any(iou(face["box"], k["box"]) > iou_thresh for k in kept):
                continue
            kept.append(face)
        return kept
