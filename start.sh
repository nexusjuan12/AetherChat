#!/bin/bash

# Activate the Conda environment
source /root/miniconda3/etc/profile.d/conda.sh
conda activate aetherchat

# Start AetherChat by running this script
./start.sh &

# Execute the webserver
python /root/webserver.py &

# Run KoboldCPP
# NOTE: Use your own model by replacing the path below with your model file path.
# Example: /root/Kobold/./koboldcpp /path/to/your-model-file.gguf --port 5000 --host 0.0.0.0 --usecublas
/root/Kobold/./koboldcpp /root/Kobold/models/L3.1-Dark-Planet-SpinFire-Uncensored-8B-D_AU-Q4_k_m.gguf --port 5000 --host 0.0.0.0 --usecublas
