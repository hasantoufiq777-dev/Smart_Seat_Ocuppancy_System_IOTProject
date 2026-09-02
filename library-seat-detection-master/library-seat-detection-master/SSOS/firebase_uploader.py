"""
Firebase Realtime Database Uploader for SSOS Gender Detection.

Pushes gender detection events from the Raspberry Pi to the same
Firebase RTDB used by the ESP32 / dashboard.

Uses the Firebase REST API with the legacy database secret (same
authentication method as the ESP32) — no service account needed.

Runs writes on a background thread to avoid blocking the camera loop.
Falls back gracefully if Firebase is unreachable.
"""

import threading
import queue
import json
from datetime import datetime

import requests
import config


class FirebaseUploader:
    """
    Non-blocking Firebase Realtime Database writer.

    Enqueues updates and processes them on a daemon thread so the
    camera / detection pipeline is never stalled by network I/O.
    """

    def __init__(self):
        self.enabled = config.FIREBASE_ENABLED
        self._queue = queue.Queue()
        self._running = False

        if not self.enabled:
            print("[Firebase] Uploader disabled via config.FIREBASE_ENABLED = False")
            return

        # Build the base URL (strip trailing slash if present)
        self._base_url = config.FIREBASE_DATABASE_URL.rstrip("/")
        self._auth = config.FIREBASE_DATABASE_SECRET

        # Quick connectivity test
        try:
            test_url = f"{self._base_url}/SmartStudySpace/Summary.json?auth={self._auth}"
            resp = requests.get(test_url, timeout=5)
            if resp.status_code == 200:
                print("[Firebase] REST API connection test PASSED [OK]")
                print(f"[Firebase] Database URL: {self._base_url}")
                self._running = True

                # Start worker thread
                self._thread = threading.Thread(target=self._worker, daemon=True)
                self._thread.start()
            else:
                print(f"[Firebase] REST API test failed (HTTP {resp.status_code}): {resp.text}")
                print("[Firebase] Continuing with CSV-only logging.")
                self.enabled = False
        except Exception as e:
            print(f"[Firebase] Connection test failed: {e}")
            print("[Firebase] Continuing with CSV-only logging.")
            self.enabled = False

    # ── Firebase REST Helpers ──────────────────────────────────

    def _patch(self, path, data):
        """PATCH (merge update) data at the given database path."""
        url = f"{self._base_url}/{path}.json?auth={self._auth}"
        resp = requests.patch(url, json=data, timeout=10)
        resp.raise_for_status()
        return resp

    def _post(self, path, data):
        """POST (push with auto-generated key) data at the given path."""
        url = f"{self._base_url}/{path}.json?auth={self._auth}"
        resp = requests.post(url, json=data, timeout=10)
        resp.raise_for_status()
        return resp

    def _get(self, path):
        """GET data at the given path."""
        url = f"{self._base_url}/{path}.json?auth={self._auth}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _put(self, path, data):
        """PUT (overwrite) data at the given path."""
        url = f"{self._base_url}/{path}.json?auth={self._auth}"
        resp = requests.put(url, json=data, timeout=10)
        resp.raise_for_status()
        return resp

    def _delete(self, path):
        """DELETE data at the given path."""
        url = f"{self._base_url}/{path}.json?auth={self._auth}"
        resp = requests.delete(url, timeout=10)
        resp.raise_for_status()
        return resp

    # ── Public API ─────────────────────────────────────────────

    def update_seat_gender(self, seat_id, event_type, gender, confidence, display_slot=None):
        """
        Queue a gender detection update for a person / seat.

        Parameters
        ----------
        seat_id : int
            Persistent track / person ID.
        event_type : str
            One of 'ENTER', 'EXIT', 'GENDER_CHANGE'.
        gender : str
            'Male' or 'Female'.
        confidence : float
            Detection confidence as a percentage (0–100), or 0 for N/A.
        display_slot : int, optional
            Left-to-right position (1-based) used to map onto FIREBASE_SEAT_MAP.
        """
        if not self.enabled:
            return

        self._queue.put({
            "action": "seat_gender",
            "seat_id": seat_id,
            "display_slot": display_slot,
            "event_type": event_type,
            "gender": gender,
            "confidence": confidence,
            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        })

    def update_gender_stats(self, seat_id, stats, display_slot=None):
        """
        Queue an update of cumulative gender session counts for a person.

        Parameters
        ----------
        seat_id : int
            Persistent track / person ID.
        stats : dict
            Dict with keys 'Male', 'Female', 'Total_Occupations'.
        display_slot : int, optional
            Left-to-right position (1-based) used to map onto FIREBASE_SEAT_MAP.
        """
        if not self.enabled:
            return

        self._queue.put({
            "action": "gender_stats",
            "seat_id": seat_id,
            "display_slot": display_slot,
            "stats": stats,
        })

    def update_live_summary(self, people_count, male_count, female_count, unknown_count):
        """Queue a live frame summary (how many people currently visible)."""
        if not self.enabled:
            return

        self._queue.put({
            "action": "live_summary",
            "people_count": people_count,
            "male_count": male_count,
            "female_count": female_count,
            "unknown_count": unknown_count,
            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        })

    def clear_gender_data(self):
        """Queue a reset of all gender data in Firebase."""
        if not self.enabled:
            return

        self._queue.put({"action": "clear_all"})

    def stop(self):
        """Signal the worker thread to finish."""
        self._running = False
        self._queue.put(None)  # Sentinel to unblock .get()

    # ── Background Worker ──────────────────────────────────────

    def _worker(self):
        """Process queued updates sequentially."""
        while self._running:
            try:
                item = self._queue.get(timeout=0.5)
                if item is None:
                    break

                action = item.get("action")

                if action == "seat_gender":
                    self._write_seat_gender(item)
                elif action == "gender_stats":
                    self._write_gender_stats(item)
                elif action == "clear_all":
                    self._write_clear_all()
                elif action == "live_summary":
                    self._write_live_summary(item)

                self._queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                print(f"[Firebase Worker] Error: {e}")

    # ── Private Write Methods ──────────────────────────────────

    def _write_seat_gender(self, item):
        """Write gender detection data for a tracked person (+ optional physical seat)."""
        conf_val = round(item["confidence"], 1) if item["confidence"] > 0 else 0
        person_key = f"Person{item['seat_id']}"
        payload = {
            "gender": item["gender"],
            "genderConfidence": conf_val,
            "genderLastEvent": item["event_type"],
            "genderLastUpdate": item["timestamp"],
            "occupied": item["event_type"] != "EXIT",
        }

        # Always store under DetectedPeople for unlimited persons
        self._patch(f"SmartStudySpace/DetectedPeople/{person_key}", payload)

        # Also mirror onto physical seats when left-to-right slot is known
        slot = item.get("display_slot")
        seat_key = config.FIREBASE_SEAT_MAP.get(slot) if slot else None
        if seat_key:
            self._patch(f"SmartStudySpace/Seats/{seat_key}", {
                "gender": item["gender"] if item["event_type"] != "EXIT" else "",
                "genderConfidence": conf_val if item["event_type"] != "EXIT" else 0,
                "genderLastEvent": item["event_type"],
                "genderLastUpdate": item["timestamp"],
            })

        self._push_event_log(item)

    def _write_gender_stats(self, item):
        """Write cumulative gender stats for a tracked person (+ optional physical seat)."""
        stats = item["stats"]
        person_key = f"Person{item['seat_id']}"
        stats_payload = {
            "maleCount": stats.get("Male", 0),
            "femaleCount": stats.get("Female", 0),
            "totalOccupations": stats.get("Total_Occupations", 0),
        }
        self._patch(f"SmartStudySpace/DetectedPeople/{person_key}/genderStats", stats_payload)

        slot = item.get("display_slot")
        seat_key = config.FIREBASE_SEAT_MAP.get(slot) if slot else None
        if seat_key:
            self._patch(f"SmartStudySpace/Seats/{seat_key}/genderStats", {
                "maleCount": stats.get("Male", 0),
                "femaleCount": stats.get("Female", 0),
            })

    def _write_live_summary(self, item):
        """Write how many people are currently visible in frame."""
        self._patch("SmartStudySpace/GenderLiveSummary", {
            "peopleCount": item["people_count"],
            "maleCount": item["male_count"],
            "femaleCount": item["female_count"],
            "unknownCount": item["unknown_count"],
            "lastUpdate": item["timestamp"],
        })

    def _push_event_log(self, item):
        """
        Push a gender event to the shared event log node.
        Trims old entries to keep only the most recent N events.
        """
        self._post("SmartStudySpace/GenderEventLog", {
            "seat": item["seat_id"],
            "displaySlot": item.get("display_slot"),
            "event": item["event_type"],
            "gender": item["gender"],
            "confidence": round(item["confidence"], 1) if item["confidence"] > 0 else 0,
            "timestamp": item["timestamp"],
        })

        # Trim old entries — keep only the most recent FIREBASE_MAX_EVENT_LOG
        try:
            snapshot = self._get("SmartStudySpace/GenderEventLog")
            if snapshot and isinstance(snapshot, dict):
                keys = sorted(snapshot.keys())
                if len(keys) > config.FIREBASE_MAX_EVENT_LOG:
                    excess = keys[:len(keys) - config.FIREBASE_MAX_EVENT_LOG]
                    for old_key in excess:
                        self._delete(f"SmartStudySpace/GenderEventLog/{old_key}")
        except Exception:
            pass  # Trimming is best-effort

    def _write_clear_all(self):
        """Remove all gender-related data from Firebase."""
        for seat_key in config.FIREBASE_SEAT_MAP.values():
            self._patch(f"SmartStudySpace/Seats/{seat_key}", {
                "gender": "",
                "genderConfidence": 0,
                "genderLastEvent": "",
                "genderLastUpdate": "",
                "genderStats": {"maleCount": 0, "femaleCount": 0},
            })

        self._delete("SmartStudySpace/DetectedPeople")
        self._delete("SmartStudySpace/GenderLiveSummary")
        self._delete("SmartStudySpace/GenderEventLog")
        print("[Firebase] All gender data cleared.")
