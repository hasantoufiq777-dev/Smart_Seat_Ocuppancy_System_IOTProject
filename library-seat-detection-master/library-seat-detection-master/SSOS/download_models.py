import os
import sys
import urllib.request

WEIGHTS_DIR = "weights"

# Model file URLs
MODELS = {
    "deploy.prototxt.txt": "https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt",
    "res10_300x300_ssd_iter_140000_fp16.caffemodel": "https://raw.githubusercontent.com/opencv/opencv_3rdparty/dnn_samples_face_detector_20180205_fp16/res10_300x300_ssd_iter_140000_fp16.caffemodel",
    "deploy_gender.prototxt": "https://huggingface.co/AjaySharma/genderDetection/resolve/main/gender_deploy.prototxt",
    "gender_net.caffemodel": "https://huggingface.co/AjaySharma/genderDetection/resolve/main/gender_net.caffemodel",
    "yolov8n.onnx": "https://huggingface.co/Shad0ws/yolov8onnx/resolve/main/yolov8n.onnx"
}

def download_file(url, filename):
    filepath = os.path.join(WEIGHTS_DIR, filename)
    
    if os.path.exists(filepath):
        # Check size if possible, or just skip if file exists
        print(f"[Exists] {filename} is already present at {filepath}. Skipping download.")
        return
        
    print(f"\n[Downloading] Fetching {filename} from {url}...")
    
    def progress_callback(blocknum, blocksize, totalsize):
        readsofar = blocknum * blocksize
        if totalsize > 0:
            percent = min(100, readsofar * 100 / totalsize)
            sys.stdout.write(f"\rProgress: {percent:.1f}% ({readsofar / (1024*1024):.2f} MB / {totalsize / (1024*1024):.2f} MB)")
            sys.stdout.flush()
        else:
            sys.stdout.write(f"\rDownloaded {readsofar / (1024*1024):.2f} MB")
            sys.stdout.flush()

    try:
        # Create weights directory if not exists
        os.makedirs(WEIGHTS_DIR, exist_ok=True)
        urllib.request.urlretrieve(url, filepath, progress_callback)
        print(f"\n[Success] Saved {filename} to {filepath}.")
    except Exception as e:
        print(f"\n[Error] Failed to download {filename}: {e}")
        # Clean up partial download
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception:
                pass
        raise e

def main():
    print("==================================================")
    print("  OpenCV DNN Model Downloader for Gender Detection")
    print("==================================================")
    
    try:
        os.makedirs(WEIGHTS_DIR, exist_ok=True)
        for filename, url in MODELS.items():
            download_file(url, filename)
        print("\n[Done] All model files are ready!")
    except Exception as e:
        print(f"\n[Failed] Download process interrupted: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
