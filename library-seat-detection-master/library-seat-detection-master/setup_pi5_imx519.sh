#!/bin/bash

# Exit immediately if any command fails
set -e

echo "=========================================================="
echo "  Raspberry Pi 5 & IMX519 Camera System Setup Guide"
echo "=========================================================="

# 1. Check if running on Raspberry Pi (Linux ARM)
if [ "$(uname -s)" != "Linux" ]; then
    echo "[Error] This setup script is intended to run on a Linux-based Raspberry Pi."
    echo "Aborting script execution."
    exit 1
fi

# 2. Configure IMX519 Camera Overlay in config.txt
CONFIG_PATH="/boot/firmware/config.txt"
if [ ! -f "$CONFIG_PATH" ]; then
    CONFIG_PATH="/boot/config.txt"
fi

echo "[System] Target configuration file: $CONFIG_PATH"

# Check if overlay is already active
if grep -q "dtoverlay=imx519" "$CONFIG_PATH"; then
    echo "[Exists] 'dtoverlay=imx519' is already configured in $CONFIG_PATH."
    REBOOT_NEEDED=false
else
    echo "[Configuring] Adding 'dtoverlay=imx519' to $CONFIG_PATH..."
    echo "This operation requires administrator privileges."
    
    # Append overlay directive to [all] section or end of file
    sudo bash -c "echo '' >> $CONFIG_PATH"
    sudo bash -c "echo '# Enable Arducam IMX519 autofocus camera module' >> $CONFIG_PATH"
    sudo bash -c "echo 'dtoverlay=imx519' >> $CONFIG_PATH"
    
    echo "[Success] Camera overlay configured!"
    REBOOT_NEEDED=true
fi

# 3. Install System Packages
echo "[Installing] Fetching system dependencies from APT..."
sudo apt update
sudo apt install -y python3-picamera2 python3-opencv python3-pip python3-venv libcamera-tools

# 4. Set up Python Virtual Environment (with access to system site packages for picamera2)
VENV_DIR="venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "[VirtualEnv] Creating a virtual environment with system site-packages access..."
    # --system-site-packages is crucial so that the system-provided python3-picamera2 (libcamera bindings) can be loaded
    python3 -m venv --system-site-packages "$VENV_DIR"
    echo "[VirtualEnv] Virtual environment created at ./$VENV_DIR"
else
    echo "[Exists] Python virtual environment already exists."
fi

# 5. Install Python dependencies
echo "[Pip] Activating virtual environment and installing packages..."
source "$VENV_DIR"/bin/activate

# Install SSOS requirements
pip install -r SSOS/requirements.txt

# Install extra legacy script dependencies (e.g. tqdm)
pip install tqdm

echo "[Success] Python requirements installed!"

# 6. Final message and reboot check
echo "----------------------------------------------------------"
echo "  Setup Completed Successfully!"
echo "----------------------------------------------------------"
if [ "$REBOOT_NEEDED" = true ]; then
    echo ">>> IMPORTANT: You MUST reboot your Raspberry Pi for the IMX519 camera overlay to load."
    echo ">>> Please run: sudo reboot"
else
    echo "You are ready to go! To run the applications:"
    echo "1. Activate venv:   source venv/bin/activate"
    echo "2. Test camera:     python test_imx519_focus.py"
    echo "3. Run main app:    python SSOS/app.py"
    echo "4. Run legacy app:  python seat_detection.py --video 0 --seat-bb-csv seat_bb_vid1.csv"
fi
echo "=========================================================="
