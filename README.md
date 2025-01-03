# AetherChat

AetherChat is an open-source character AI chat platform that combines text generation using a local OpenAI style API, with voice synthesis to create interactive character conversations. Users can create custom characters with unique voices, appearance, and personalities. 


I've setup a demo of the finished project after deployment use test/test for credentials. http://111.59.36.106:30802 

## Features

- **Character Creation**:
  - Custom avatars (static) and character backgrounds (static or video)
  - Microsoft Edge TTS voice selection
  - RVC (Retrieval-based Voice Conversion) voice model integration and custom model upload
  - Customizable initial greetings
  - Configurable system prompts
  - Adjustable voice parameters (pitch and rate)
  - Adjustable text generation paramaters 

- **Chat Interface**:
  - Real-time text and voice responses
  - Background media display
  - Adjustable AI parameters per session
  - Voice toggle options

- **Technical Features**:
  - KoboldCPP integration for text generation (should work with any local OpenAI style API on port 5000) comes with sample text generation model or bring your own
  - Microsoft Edge TTS + RVC for voice synthesis
  - Flask-based web server
  - CUDA acceleration support
  - Responsive web design

## Requirements

- Ubuntu 22.04 (recommended)
- CUDA 12.1
- Python 3.10
- At least 8GB RAM
- NVIDIA GPU with CUDA support tested on 12gb VRAM(recommended)

## Quick Start

### Automated Installation

1. Download `setup.sh` and `requirements.txt` to your installation directory
2. Make the setup script executable:
   ```bash
   chmod +x setup.sh
   ```
3. Run the setup script:
   ```bash
   ./setup.sh
   ```
4. Start KoboldCPP:
   ```bash
   cd /root/Kobold
   ./koboldcpp /root/Kobold/models/L3.1-Dark-Planet-SpinFire-Uncensored-8B-D_AU-Q4_k_m.gguf --port 5000 --host 0.0.0.0 --usecublas
   ```
5. In a new terminal, activate the conda environment:
   ```bash
   source /root/miniconda3/bin/activate aetherchat
   ```
6. Start the web server:
   ```bash
   cd /root
   python webserver.py
   ```
7. Access the application in your web browser at localhost port 8081 `http://127.0.0.1:8081`
   admin credentials are admin/admin admin dashboard can be found in the side panel in the my-library screen.

### Manual Installation 

1. **System Dependencies**
   ```bash
   sudo apt update
   sudo apt install -y build-essential gcc g++ make cmake python3 python3-pip python3-venv \
   ffmpeg libsndfile1 portaudio19-dev python3-dev unrar p7zip-full libgl1-mesa-glx libasound2-dev
   ```

2. **Install Miniconda**
   ```bash
   wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
   chmod +x Miniconda3-latest-Linux-x86_64.sh
   ./Miniconda3-latest-Linux-x86_64.sh -b -p /root/miniconda3
   eval "$(/root/miniconda3/bin/conda shell.bash hook)"
   /root/miniconda3/bin/conda init bash
   source ~/.bashrc
   ```

3. **Create and Activate Conda Environment**
   ```bash
   conda create -n aetherchat python=3.10 -y
   source /root/miniconda3/bin/activate aetherchat
   pip install pip==24.0
   ```
   4. **Create Directory Structure**
   ```bash
   mkdir -p /root/{models,output,input,Kobold,templates,db}
   ```

5. **Install KoboldCPP**
   ```bash
   cd /root/Kobold
   wget https://github.com/LostRuins/koboldcpp/releases/download/v1.79.1/koboldcpp-linux-x64-cuda1210
   chmod +x koboldcpp-linux-x64-cuda1210
   mkdir models
   cd models
   wget https://huggingface.co/DavidAU/L3.1-Dark-Planet-SpinFire-Uncensored-8B-GGUF/resolve/main/L3.1-Dark-Planet-SpinFire-Uncensored-8B-D_AU-Q4_k_m.gguf
   ```

6. **Clone Repository and Setup Files**
   ```bash
   git clone https://github.com/nexusjuan12/AetherChat.git /root/main
   cp main/env_backup_root /root/.env
   cp -r main/templates /root/
   cp main/webserver.py /root/
   cp main/queue_system.py /root/
   cp -r main/db /root/
   chmod 644 /root/db/users.db
   chown root:root /root/db/users.db
   ```

7. **Install PyTorch and Dependencies**
   ```bash
   pip install torch==2.5.1+cu121 torchvision==0.20.1+cu121 torchaudio==2.5.1+cu121 --index-url https://download.pytorch.org/whl/cu121
   
   # Install RVC and TTS
   python -m pip install git+https://github.com/Atm4x/tts-with-rvc.git#egg=tts_with_rvc
   python -m pip install git+https://github.com/Atm4x/rvc-lib.git@dev#egg=rvc
   python -m pip install -e git+https://github.com/Atm4x/rvc-lib.git#egg=rvclib
   python -m pip install git+https://github.com/Atm4x/rvc-tts-pipeline-fix.git@dev#egg=rvc_tts_pipe
   
   # Install remaining requirements
   cd /root/main
   pip install -r requirements.txt
   ```

8. **Download Models**
   ```bash
   pip install huggingface_hub
   python3 -c "from huggingface_hub import snapshot_download; snapshot_download('nexusjuan/Aetherchat', local_dir='/root/', repo_type='model')"
   ```

   
## Usage

1. **Start KoboldCPP**
   ```bash
   cd /root/Kobold
   ./koboldcpp models/L3.1-Dark-Planet-SpinFire-Uncensored-8B-D_AU-Q4_k_m.gguf --port 5000 --host 0.0.0.0 --usecublas
   ```

2. **Start Web Server**
   In a new terminal:
   ```bash
   source /root/miniconda3/bin/activate aetherchat
   cd /root
   python webserver.py
   ```

3. Access the application at `http://127.0.0.1:8081`

4. From the landing page you can login using the admin credentials admin/admin

## Character Creation

1. Click "Create Character" on the main page
2. Upload an avatar image
3. Choose a Microsoft Edge TTS voice
4. Upload or select an RVC voice model
5. Set voice parameters (pitch and rate)
6. Add character description and system prompt
7. Set initial greetings
8. Upload background image or video 

## Troubleshooting

- Ensure CUDA is properly installed and configured
- Check that all required directories exist and have proper permissions
- Verify KoboldCPP is running before starting the web server
- Monitor the terminal output for any error messages
- Ensure all models are downloaded correctly

## Notes

- admin account for web interface is admin/admin
- The default model is suitable for general conversation but you can use any GGUF format model compatible with KoboldCPP
- Character creation includes both public and private options
- Voice synthesis requires both TTS and RVC models
- Background videos support common formats (mp4, webm, etc.)
- The server should work with any local OpenAI style API available on port 5000

## License

## License
This project is licensed under the [Creative Commons BY-NC](LICENSE).

This version is provided as-is for personal and non-commercial use. The final commercial version will include additional features and licensing options.


## Acknowledgments
- Atm4x for his great work https://github.com/Atm4x/tts-with-rvc
- KoboldCPP for the text generation backend
- Microsoft Edge TTS for base voice synthesis
- RVC for voice conversion
- All other open-source contributors
