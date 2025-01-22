#!/bin/bash

# Function to clean up and exit on error
handle_error() {
    echo "Error occurred: $1"
    pkill -f webserver.py  # Kill any running webserver processes
    exit 1
}

# Increase thread/process limits for this session
ulimit -u 65536

# Activate the Conda environment
source /root/miniconda3/etc/profile.d/conda.sh
conda activate aetherchat || handle_error "Failed to activate Conda environment"

# Start Flask webserver
python /root/webserver.py &
WEB_SERVER_PID=$!
echo "Started webserver.py (PID: $WEB_SERVER_PID)"

# Wait for a few seconds to ensure the server initializes
sleep 5

# Check if the webserver is running
if ! ps -p $WEB_SERVER_PID > /dev/null; then
    handle_error "Webserver failed to start"
fi

# Run KoboldCPP with error handling
# NOTE: Replace with your model path
/root/Kobold/./koboldcpp /root/Kobold/models/L3.1-Dark-Planet-SpinFire-Uncensored-8B-D_AU-Q4_k_m.gguf --port 5000 --host 0.0.0.0 --usecublas || handle_error "KoboldCPP failed to start"

# Wait for both processes to run
wait $WEB_SERVER_PID
