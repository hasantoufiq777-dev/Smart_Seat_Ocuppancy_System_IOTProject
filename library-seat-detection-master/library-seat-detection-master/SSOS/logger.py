import os
import csv
from datetime import datetime
from collections import defaultdict

import config
from firebase_uploader import FirebaseUploader


def _empty_stats():
    return {"Male": 0, "Female": 0, "Total_Occupations": 0}


class SeatLogger:
    def __init__(self, filepath=None):
        self.filepath = filepath or config.LOG_FILE_PATH
        self.headers = ["Timestamp", "Seat", "Event", "Gender", "Confidence"]
        self._initialize_csv()

        # Historical session statistics keyed by person / track id
        self.stats = defaultdict(_empty_stats)
        self._load_existing_stats()

        # Firebase uploader (non-blocking background thread)
        self.firebase = FirebaseUploader()

    def _initialize_csv(self):
        """Creates the log file with headers if it does not already exist."""
        if not os.path.exists(self.filepath):
            try:
                with open(self.filepath, mode='w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(self.headers)
                print(f"[Logger] Initialized new log file at: {self.filepath}")
            except Exception as e:
                print(f"[Logger] Error creating log file: {e}")

    def _load_existing_stats(self):
        """Reads the existing log file to reconstruct session history statistics."""
        if not os.path.exists(self.filepath):
            return

        try:
            with open(self.filepath, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        person_id = int(row.get("Seat", 0))
                    except (TypeError, ValueError):
                        continue
                    if person_id <= 0:
                        continue

                    event = row.get("Event", "")
                    gender = row.get("Gender", "")

                    if event == "ENTER":
                        self.stats[person_id]["Total_Occupations"] += 1
                        if gender in ("Male", "Female"):
                            self.stats[person_id][gender] += 1
                    elif event == "GENDER_CHANGE":
                        if gender in ("Male", "Female"):
                            self.stats[person_id][gender] += 1
        except Exception as e:
            print(f"[Logger] Warning: Could not parse existing log stats: {e}")

    def log_event(self, person_id: int, event_type: str, gender: str, confidence: float,
                  display_slot: int = None):
        """
        Logs a transition event to the CSV file AND pushes to Firebase.
        event_type can be: 'ENTER', 'EXIT', or 'GENDER_CHANGE'
        person_id: persistent track id
        display_slot: optional left-to-right index (1-based) for Firebase seat mapping
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conf_str = f"{confidence:.1f}%" if confidence > 0 else "N/A"

        row = [timestamp, person_id, event_type, gender, conf_str]

        try:
            with open(self.filepath, mode='a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(row)

            if event_type == "ENTER":
                self.stats[person_id]["Total_Occupations"] += 1
                if gender in ("Male", "Female"):
                    self.stats[person_id][gender] += 1
            elif event_type == "GENDER_CHANGE":
                if gender in ("Male", "Female"):
                    self.stats[person_id][gender] += 1

            print(
                f"[Logger] Event recorded: {timestamp} | Person {person_id} | "
                f"{event_type} | {gender} ({conf_str})"
            )

            self.firebase.update_seat_gender(
                person_id, event_type, gender, confidence, display_slot=display_slot
            )
            self.firebase.update_gender_stats(
                person_id, dict(self.stats[person_id]), display_slot=display_slot
            )

        except Exception as e:
            print(f"[Logger] Error writing to log file: {e}")

    def get_stats(self, person_id: int):
        """Returns the stats for a given person / track id."""
        return self.stats.get(person_id, _empty_stats())

    def get_totals(self):
        """Aggregate Male/Female/Total across all persons this session."""
        totals = _empty_stats()
        for s in self.stats.values():
            totals["Male"] += s["Male"]
            totals["Female"] += s["Female"]
            totals["Total_Occupations"] += s["Total_Occupations"]
        return totals

    def clear_logs(self):
        """Clears the log file, resets stats, and clears Firebase gender data."""
        try:
            with open(self.filepath, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(self.headers)
            self.stats = defaultdict(_empty_stats)

            self.firebase.clear_gender_data()

            print("[Logger] Logs cleared successfully.")
        except Exception as e:
            print(f"[Logger] Error clearing logs: {e}")

    def stop(self):
        """Stop the Firebase uploader background thread."""
        self.firebase.stop()
