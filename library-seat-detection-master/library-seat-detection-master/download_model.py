import os
import urllib.request
import tarfile
import shutil

MODEL_URL = "http://download.tensorflow.org/models/object_detection/faster_rcnn_inception_v2_coco_2018_01_28.tar.gz"
TAR_FILE = "faster_rcnn_inception_v2_coco_2018_01_28.tar.gz"
EXTRACT_DIR = "faster_rcnn_inception_v2_coco_2018_01_28"
TARGET_DIR = os.path.join("models", "faster_rcnn_inception_v2")
TARGET_PB = os.path.join(TARGET_DIR, "frozen_inference_graph.pb")

def main():
    # 1. Create target directories
    os.makedirs(TARGET_DIR, exist_ok=True)
    
    # 2. Download model archive
    if not os.path.exists(TAR_FILE) and not os.path.exists(TARGET_PB):
        print("Downloading pre-trained Faster R-CNN model (approx. 149 MB)...")
        try:
            urllib.request.urlretrieve(MODEL_URL, TAR_FILE)
            print("Download completed successfully!")
        except Exception as e:
            print(f"Error downloading the model: {e}")
            return
    
    # 3. Extract frozen graph
    if os.path.exists(TAR_FILE):
        print("Extracting model archive...")
        try:
            with tarfile.open(TAR_FILE, "r:gz") as tar:
                # Find frozen_inference_graph.pb in tar members
                member = tar.getmember(f"{EXTRACT_DIR}/frozen_inference_graph.pb")
                # Extract it
                tar.extract(member)
            
            # Move it to the target directory
            src_pb = os.path.join(EXTRACT_DIR, "frozen_inference_graph.pb")
            if os.path.exists(src_pb):
                shutil.move(src_pb, TARGET_PB)
                print(f"Model successfully saved to: {TARGET_PB}")
                
            # Clean up extraction directory and tar file
            if os.path.exists(EXTRACT_DIR):
                shutil.rmtree(EXTRACT_DIR)
            if os.path.exists(TAR_FILE):
                os.remove(TAR_FILE)
                
        except Exception as e:
            print(f"Error during extraction: {e}")
            return
            
    if os.path.exists(TARGET_PB):
        print("\nModel is ready!")
        print(f"You can now run: python seat_detection.py --video 0 --seat-bb-csv seat_bb_vid1.csv --pretrained-model {TARGET_PB}")
    else:
        print("Failed to prepare model.")

if __name__ == "__main__":
    main()
