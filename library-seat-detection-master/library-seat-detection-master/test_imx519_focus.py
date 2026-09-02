import sys
import os
import time
import cv2

# Add SSOS directory to path to use config if needed
sys.path.append(os.path.abspath("SSOS"))

class IMX519Tester:
    def __init__(self, width=1280, height=720):
        self.width = width
        self.height = height
        self.use_picam = False
        self.picam = None
        self.cap = None
        
        # Check if we are running on Linux (Raspberry Pi 5)
        if sys.platform.startswith("linux"):
            try:
                print("[Tester] Attempting to import Picamera2...")
                from picamera2 import Picamera2
                from libcamera import controls
                self.controls = controls
                
                print("[Tester] Initializing Picamera2...")
                self.picam = Picamera2()
                config_preview = self.picam.create_preview_configuration(main={"size": (width, height)})
                self.picam.configure(config_preview)
                self.picam.start()
                
                self.use_picam = True
                print("[Tester] Native Pi Camera initialized successfully via Picamera2.")
                
                # Check control metadata
                try:
                    meta = self.picam.camera_controls
                    print("[Tester] Supported controls:", list(meta.keys()))
                except Exception as meta_err:
                    print("[Tester] Could not read camera controls list:", meta_err)
            except Exception as e:
                print(f"[Tester] Picamera2 init failed: {e}")
                print("[Tester] Falling back to standard OpenCV VideoCapture...")
        
        if not self.use_picam:
            print("[Tester] Using standard OpenCV VideoCapture on index 0...")
            self.cap = cv2.VideoCapture(0)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            
    def run(self):
        if self.use_picam:
            self._run_picam()
        else:
            self._run_cv()
            
    def _run_picam(self):
        print("\n==============================================")
        # Check if AfMode control exists in self.controls
        af_mode_supported = hasattr(self.controls, "AfModeEnum")
        print(f"  Pi Camera test screen running.")
        print("  Controls:")
        print("    - Press 'F' to trigger a one-shot Autofocus cycle.")
        print("    - Press '[' (decrease) and ']' (increase) to adjust Lens Position manually.")
        print("    - Press 'C' to set autofocus to Continuous (CAF).")
        print("    - Press 'M' to set focus mode to Manual.")
        print("    - Press 'Q' or ESC to QUIT.")
        print("==============================================\n")
        
        lens_pos = 0.0  # units of dioptres (1/distance in meters), 0.0 is infinity
        mode = "Auto/Continuous"
        
        # Enable continuous autofocus at start if possible
        try:
            self.picam.set_controls({"AfMode": self.controls.AfModeEnum.Continuous})
            print("[Tester] Set initial focus mode to Continuous Autofocus")
        except Exception as e:
            print(f"[Tester] Continuous autofocus not supported: {e}")
            mode = "Manual (fallback)"
            
        while True:
            try:
                frame = self.picam.capture_array()
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            except Exception as e:
                print(f"[Tester Capture Error] {e}")
                break
                
            # Render HUD overlay on the frame
            h, w = frame.shape[:2]
            cv2.rectangle(frame, (10, 10), (450, 130), (30, 30, 30), -1)
            cv2.rectangle(frame, (10, 10), (450, 130), (80, 240, 80), 1)
            
            cv2.putText(frame, "IMX519 Focus Diagnostic Tool", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(frame, f"Resolution: {w}x{h}", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)
            cv2.putText(frame, f"Focus Mode: {mode}", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)
            cv2.putText(frame, f"Lens Position (Manual): {lens_pos:.2f} dioptres", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (80, 240, 80), 1, cv2.LINE_AA)
            cv2.putText(frame, "F: Trigger AF Cycle | M: Manual | C: Continuous | [ ]: Lens Pos", (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (120, 120, 120), 1, cv2.LINE_AA)
            
            cv2.imshow("IMX519 Focus Test", frame)
            
            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), ord('Q'), 27):
                break
            elif key in (ord('f'), ord('F')):
                print("[Tester] Triggering one-shot autofocus cycle...")
                try:
                    # Switch to Auto first to trigger
                    self.picam.set_controls({"AfMode": self.controls.AfModeEnum.Auto})
                    success = self.picam.autofocus_cycle()
                    mode = "Auto (One-Shot Cycle)"
                    if success:
                        print("[Tester] Focus cycle: SUCCESS")
                    else:
                        print("[Tester] Focus cycle: FAILED")
                except Exception as af_err:
                    print(f"[Tester] Focus cycle failed to execute: {af_err}")
            elif key in (ord('c'), ord('C')):
                print("[Tester] Switching to Continuous Autofocus...")
                try:
                    self.picam.set_controls({"AfMode": self.controls.AfModeEnum.Continuous})
                    mode = "Continuous"
                except Exception as err:
                    print(f"[Tester] Failed to set continuous autofocus: {err}")
            elif key in (ord('m'), ord('M')):
                print("[Tester] Switching to Manual Focus mode...")
                try:
                    self.picam.set_controls({"AfMode": self.controls.AfModeEnum.Manual})
                    mode = "Manual"
                except Exception as err:
                    print(f"[Tester] Failed to set manual autofocus mode: {err}")
            elif key == ord('['):
                lens_pos = max(0.0, lens_pos - 0.25)
                print(f"[Tester] Setting Manual Lens Position: {lens_pos:.2f}")
                try:
                    self.picam.set_controls({"AfMode": self.controls.AfModeEnum.Manual})
                    self.picam.set_controls({"LensPosition": lens_pos})
                    mode = "Manual"
                except Exception as err:
                    print(f"[Tester] Failed to set lens position: {err}")
            elif key == ord(']'):
                lens_pos = min(15.0, lens_pos + 0.25)
                print(f"[Tester] Setting Manual Lens Position: {lens_pos:.2f}")
                try:
                    self.picam.set_controls({"AfMode": self.controls.AfModeEnum.Manual})
                    self.picam.set_controls({"LensPosition": lens_pos})
                    mode = "Manual"
                except Exception as err:
                    print(f"[Tester] Failed to set lens position: {err}")
                    
        self.release()

    def _run_cv(self):
        print("\n==============================================")
        print("  OpenCV VideoCapture test screen running.")
        print("  Controls:")
        print("    - Press 'Q' or ESC to QUIT.")
        print("==============================================\n")
        
        while True:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                print("[Tester Error] Failed to read frame from VideoCapture.")
                break
                
            h, w = frame.shape[:2]
            cv2.rectangle(frame, (10, 10), (350, 80), (30, 30, 30), -1)
            cv2.rectangle(frame, (10, 10), (350, 80), (80, 240, 80), 1)
            cv2.putText(frame, "VideoCapture Diagnostic Screen", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(frame, f"Resolution: {w}x{h}", (20, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)
            cv2.putText(frame, "Standard VideoCapture (Non-Pi Host)", (20, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (120, 120, 120), 1, cv2.LINE_AA)
            
            cv2.imshow("IMX519 Focus Test (CV Fallback)", frame)
            
            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), ord('Q'), 27):
                break
                
        self.release()
        
    def release(self):
        if self.picam is not None:
            try:
                self.picam.stop()
                self.picam.close()
                print("[Tester] Released Pi Camera.")
            except Exception:
                pass
            self.picam = None
        if self.cap is not None:
            self.cap.release()
            print("[Tester] Released VideoCapture.")
        cv2.destroyAllWindows()

if __name__ == "__main__":
    tester = IMX519Tester()
    tester.run()
