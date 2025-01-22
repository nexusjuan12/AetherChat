#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status

# Function to clean up and exit gracefully
cleanup() {
    echo "Stopping running processes..."
    pkill -f webserver.py || true
    exit 1
}
trap cleanup SIGTERM SIGINT

# Ensure the logs directory exists
mkdir -p /root/logs

# Activate Conda environment
source /root/miniconda3/etc/profile.d/conda.sh
conda activate aetherchat || { echo "Failed to activate Conda environment"; exit 1; }

# Start Flask webserver and redirect output to a log file
echo "Starting Flask webserver..."
python /root/webserver.py > /root/logs/webserver.log 2>&1 &
WEB_SERVER_PID=$!
echo "Webserver started with PID: $WEB_SERVER_PID"

# Wait for the webserver to initialize
sleep 5

# Check if the webserver is still running
if ! ps -p $WEB_SERVER_PID > /dev/null; then
    echo "Webserver failed to start. Exiting."
    cleanup
fi

# Start KoboldCPP and redirect output to a log file
echo "Starting KoboldCPP..."
/root/Kobold/./koboldcpp /root/Kobold/models/L3.1-Dark-Planet-SpinFire-Uncensored-8B-D_AU-Q4_k_m.gguf --port 5000 --host 0.0.0.0 --usecublas > /root/logs/koboldcpp.log 2>&1 || {
    echo "KoboldCPP failed to start. Exiting."
    cleanup
}

# Wait for both processes
wait $WEB_SERVER_PID
