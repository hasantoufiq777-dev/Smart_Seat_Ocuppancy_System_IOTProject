import cv2
import numpy as np
from object_detector import ObjectDetector

IMAGE_PATH = r"C:\Users\ASUS\.gemini\antigravity\brain\610e4053-f25e-43dc-a7b6-05f86b446c9a\media__1784188100907.jpg"
MODEL_PATH = "models/faster_rcnn_inception_v2/frozen_inference_graph.pb"

def main():
    obj_detector = ObjectDetector(MODEL_PATH)
    img = cv2.imread(IMAGE_PATH)
    if img is None:
        print("Failed to load image.")
        return
        
    boxes, scores, classes, num = obj_detector.processFrame(img)
    
    print("Detections:")
    detected_chairs = []
    for i in range(len(boxes)):
        box = boxes[i] # (y0, x0, y1, x1)
        score = scores[i]
        cls = classes[i]
        
        if score > 0.3:
            y0, x0, y1, x1 = box
            if cls == 62: # chair
                detected_chairs.append((score, [x0, y0, x1, y1]))
            print(f"Class: {cls}, Score: {score:.4f}, Box: [x0={x0}, y0={y0}, x1={x1}, y1={y1}]")

if __name__ == "__main__":
    main()
