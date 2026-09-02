// ═══════════════════════════════════════════════════════════════
// Firebase v9+ Modular SDK — Configuration & Initialization
// ═══════════════════════════════════════════════════════════════

import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import { getDatabase, ref, onValue, off } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-database.js";

// ── Firebase Project Configuration ────────────────────────────
// Replace these placeholder values with your actual Firebase
// project credentials from the Firebase Console → Project Settings.
const firebaseConfig = {
  apiKey: "AIzaSyCO3tKfObKHZ2fCyFPY4m7Eh_4wZTh3TIY",
  authDomain: "smartstudyspace-library.firebaseapp.com",
  databaseURL: "https://smartstudyspace-library-default-rtdb.asia-southeast1.firebasedatabase.app",
  projectId: "smartstudyspace-library",
  storageBucket: "smartstudyspace-library.firebasestorage.app",
  messagingSenderId: "657596735307",
  appId: "1:657596735307:web:b957ec57a938649fe3d2ce"
};

// ── Initialize Firebase ───────────────────────────────────────
const app = initializeApp(firebaseConfig);
const database = getDatabase(app);

// ── Export for other modules ──────────────────────────────────
export { app, database, ref, onValue, off };
