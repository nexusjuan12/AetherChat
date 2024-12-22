#!/bin/bash

# Install system dependencies
sudo apt update
sudo apt install -y build-essential gcc g++ make cmake python3 python3-pip python3-venv ffmpeg libsndfile1 portaudio19-dev python3-dev unrar p7zip-full libgl1-mesa-glx libasound2-dev

# Install Miniconda
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
chmod +x Miniconda3-latest-Linux-x86_64.sh
./Miniconda3-latest-Linux-x86_64.sh -b -p /root/miniconda3
source /root/miniconda3/bin/activate

# Create and activate conda environment
conda create -n aetherchat python=3.10 -y
conda activate aetherchat
pip install pip==24.0

# Create directory structure
mkdir -p /root/models
mkdir -p /root/output
mkdir -p /root/main/avatars
mkdir -p /root/main/characters
mkdir -p /root/Kobold
mkdir -p /root/templates
mkdir -p /root/db
chmod 644 /root/db/users.db
chown root:root /root/db/users.db

# Download KoboldCPP
cd /root/Kobold
wget https://github.com/LostRuins/koboldcpp/releases/download/v1.79.1/koboldcpp-linux-x64-cuda1210
chmod +x koboldcpp-linux-x64-cuda1210
cd ..

# Clone repository and setup files
git clone https://github.com/nexusjuan12/youraiwaifv2.git
mv youraiwaifv2 main
cp main/env_backup_root /root/.env
cp main/env_backup /root/main/.env
cp -r main/templates /root/
cp main/webserver.py /root/
cp main/queue_system.py /root/
cp -r main/db /root/db

# Install PyTorch
pip install torch==2.5.1+cu121 torchvision==0.20.1+cu121 torchaudio==2.5.1+cu121 --index-url https://download.pytorch.org/whl/cu121

# Install RVC and TTS
python -m pip install git+https://github.com/Atm4x/tts-with-rvc.git#egg=tts_with_rvc
python -m pip install git+https://github.com/Atm4x/rvc-lib.git@dev#egg=rvc
python -m pip install -e git+https://github.com/Atm4x/rvc-lib.git#egg=rvclib
python -m pip install git+https://github.com/Atm4x/rvc-tts-pipeline-fix.git@dev#egg=rvc_tts_pipe

# Install remaining requirements
pip install -r requirements.txt