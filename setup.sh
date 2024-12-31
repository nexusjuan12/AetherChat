#!/bin/bash

# Install system dependencies
sudo apt update
sudo apt install -y build-essential gcc g++ make cmake python3 python3-pip python3-venv ffmpeg libsndfile1 portaudio19-dev python3-dev unrar p7zip-full libgl1-mesa-glx libasound2-dev

# Install Miniconda
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
chmod +x Miniconda3-latest-Linux-x86_64.sh
./Miniconda3-latest-Linux-x86_64.sh -b -p /root/miniconda3

# Initialize conda in the current shell
eval "$(/root/miniconda3/bin/conda shell.bash hook)"

# Initialize conda for future shell sessions
/root/miniconda3/bin/conda init bash

# Source bashrc to ensure conda commands are available
source ~/.bashrc

# Create conda environment
conda create -n aetherchat python=3.10 -y

# Activate conda environment
source /root/miniconda3/bin/activate aetherchat

# Verify we're in the right environment
echo "Python location: $(which python)"
echo "Python version: $(python --version)"
echo "Current conda env: $CONDA_DEFAULT_ENV"

# Install pip 24.0 first
pip install pip==24.0

# Create directory structure
mkdir -p /root/models
mkdir -p /root/output
mkdir -p /root/input
mkdir -p /root/Kobold
mkdir -p /root/templates
mkdir -p /root/db

# Download KoboldCPP
cd /root/Kobold
wget -O koboldcpp https://github.com/LostRuins/koboldcpp/releases/download/v1.79.1/koboldcpp-linux-x64-cuda1210
chmod +x koboldcpp
mkdir models
cd models
wget https://huggingface.co/DavidAU/L3.1-Dark-Planet-SpinFire-Uncensored-8B-GGUF/resolve/main/L3.1-Dark-Planet-SpinFire-Uncensored-8B-D_AU-Q4_k_m.gguf
cd /root

# Clone repository and setup files
git clone https://github.com/nexusjuan12/AetherChat.git /root/main
cp main/env_backup_root /root/.env
cp -r main/templates /root/
cp main/webserver.py /root/
cp main/queue_system.py /root/
cp -r main/db /root/
cp main/rmvpe.pt /root/
cp main/hubert_base.pt /root/
chmod 644 /root/db/users.db
chown root:root /root/db/users.db

# Install PyTorch in the conda environment
pip install torch==2.5.1+cu121 torchvision==0.20.1+cu121 torchaudio==2.5.1+cu121 --index-url https://download.pytorch.org/whl/cu121

# Install RVC and TTS in the conda environment
python -m pip install git+https://github.com/Atm4x/tts-with-rvc.git#egg=tts_with_rvc
python -m pip install git+https://github.com/Atm4x/rvc-lib.git@dev#egg=rvc
python -m pip install -e git+https://github.com/Atm4x/rvc-lib.git#egg=rvclib
python -m pip install git+https://github.com/Atm4x/rvc-tts-pipeline-fix.git@dev#egg=rvc_tts_pipe

# Install remaining requirements in the conda environment
pip install -r requirements.txt

# Install huggingface_hub for model downloads
pip install huggingface_hub

# Python script to download Hugging Face models
python3 - <<EOF
from huggingface_hub import snapshot_download

# Define repository and download location
repo_id = "nexusjuan/Aetherchat"
local_dir = "/root/"

# Download the repository's contents
snapshot_download(repo_id, local_dir=local_dir, repo_type="model")
EOF

cp models/rmvpe.pt /root/
cp models/hubert_base.pt /root/
# Print final environment info
echo "Installation complete. Final environment check:"
echo "Python location: $(which python)"
echo "Pip location: $(which pip)"
echo "Python version: $(python --version)"
echo "Current conda env: $CONDA_DEFAULT_ENV"

# Display activation instructions
echo -e "\nTo activate the conda environment, run:"
echo "source ~/.bashrc"
echo "conda activate aetherchat"
