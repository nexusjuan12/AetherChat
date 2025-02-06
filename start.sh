#!/bin/bash
set -e  # Exit on any error

# ======= CONFIGURABLE VARIABLES =======
# Change these values to modify the setup
# Conda environment name
CONDA_ENV="aetherchat"

# Flask Webserver script
WEBSERVER_SCRIPT="/root/webserver.py"

# KoboldCPP Binary
KOBOLDCPP_BINARY="/root/Kobold/koboldcpp"

# Language Model (GGUF file) - Change to use a different model
LLM_MODEL="/root/Kobold/models/DevQuasar-R1-Uncensored-Llama-8B.i1-Q4_K_M.gguf"

# Image Generation Configuration
ENABLE_IMAGE_GEN=true  # Set to false to disable image generation
SD_MODEL="/root/Kobold/sd/sdxlYamersRealisticNSFW_v5TX.safetensors"

# Network Configuration
PORT=5000
HOST="0.0.0.0"

# Additional KoboldCPP Options
USE_CUBLAS="--usecublas"
MULTIPLAYER="--multiplayer"

# Logs Directory
LOGS_DIR="/root/logs"

# ======= FUNCTION: CLEANUP =======
cleanup() {
    echo "Stopping running processes..."
    pkill -f "$WEBSERVER_SCRIPT" || true
    exit 1
}
trap cleanup SIGTERM SIGINT

# ======= SETUP =======
echo "Ensuring logs directory exists..."
mkdir -p "$LOGS_DIR"

# Activate Conda environment
echo "Activating Conda environment: $CONDA_ENV"
source /root/miniconda3/etc/profile.d/conda.sh
conda activate "$CONDA_ENV" || { echo "Failed to activate Conda environment"; exit 1; }

# ======= START FLASK WEBSERVER =======
echo "Starting Flask webserver..."
python "$WEBSERVER_SCRIPT" > "$LOGS_DIR/webserver.log" 2>&1 &
WEB_SERVER_PID=$!
echo "Webserver started with PID: $WEB_SERVER_PID"

# Give it time to start
sleep 5

# Check if the webserver is running
if ! ps -p $WEB_SERVER_PID > /dev/null; then
    echo "Webserver failed to start. Exiting."
    cleanup
fi

# ======= START KOBOLDCPP =======
echo "Starting KoboldCPP with model: $LLM_MODEL..."

# Build KoboldCPP command based on configuration
KOBOLD_CMD="$KOBOLDCPP_BINARY $LLM_MODEL --port $PORT --host $HOST $USE_CUBLAS $MULTIPLAYER"

# Add SD model only if image generation is enabled
if [ "$ENABLE_IMAGE_GEN" = true ] && [ -f "$SD_MODEL" ]; then
    echo "Image generation enabled, using model: $SD_MODEL"
    KOBOLD_CMD="$KOBOLD_CMD --sdmodel $SD_MODEL"
else
    echo "Image generation disabled or SD model not found"
fi

# Execute KoboldCPP with final command
$KOBOLD_CMD > "$LOGS_DIR/koboldcpp.log" 2>&1 || {
    echo "KoboldCPP failed to start. Exiting."
    cleanup
}

# ======= WAIT FOR PROCESSES =======
wait $WEB_SERVER_PID
