from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from tts_with_rvc import TTS_RVC
import requests
import os
import time
import uuid

app = Flask(__name__)
CORS(app)

# Directory for generated audio files
output_directory = "/root/output/"
os.makedirs(output_directory, exist_ok=True)

@app.route('/v1/chat/completions', methods=['POST', 'OPTIONS'])
def chat_completions():
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        data = request.json
        kobold_response = requests.post('http://localhost:5000/v1/chat/completions', 
                                      json=data)
        
        if not kobold_response.ok:
            raise Exception(f"Kobold API error: {kobold_response.status_code}")
            
        return jsonify(kobold_response.json())
    except Exception as e:
        print(f"Chat Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/tts', methods=['POST'])
def tts():
    try:
        data = request.json
        text = data.get("text")
        rvc_model = data.get("rvc_model")
        edge_voice = data.get("edge_voice")

        print(f"Received TTS request:")
        print(f"Text: {text}")
        print(f"RVC Model: {rvc_model}")
        print(f"Edge Voice: {edge_voice}")

        if not text or not rvc_model or not edge_voice:
            return jsonify({"error": "Text, rvc_model, and edge_voice are required"}), 400

        # Generate unique filename
        unique_id = str(uuid.uuid4())
        output_filename = f"response_{unique_id}.wav"
        output_path = os.path.join(output_directory, output_filename)

        # Clean up old files (keep last 10)
        cleanup_old_files()

        model_path = f"/root/models/{rvc_model}/{rvc_model}.pth"
        index_path = f"/root/models/{rvc_model}/{rvc_model}.index"

        print(f"Generating audio to: {output_path}")

        tts = TTS_RVC(
            rvc_path="src/rvclib",
            model_path=model_path,
            input_directory="/root/input/",
            index_path=index_path
        )
        
        tts.set_voice(edge_voice)
        
        tts(
            text=text,
            pitch=6,
            index_rate=0.9,
            output_filename=output_path
        )

        return jsonify({"audio_url": f"/audio/{output_filename}"}), 200
    except Exception as e:
        print(f"TTS Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

def cleanup_old_files(keep_last=10):
    """Clean up old audio files, keeping only the most recent ones"""
    try:
        files = [f for f in os.listdir(output_directory) if f.endswith('.wav')]
        files.sort(key=lambda x: os.path.getmtime(os.path.join(output_directory, x)), reverse=True)
        
        # Remove all but the last 'keep_last' files
        for f in files[keep_last:]:
            try:
                os.remove(os.path.join(output_directory, f))
            except Exception as e:
                print(f"Error removing file {f}: {e}")
                
    except Exception as e:
        print(f"Error during cleanup: {e}")

@app.route('/audio/<filename>', methods=['GET'])
def get_audio(filename):
    file_path = os.path.join(output_directory, filename)
    if os.path.exists(file_path):
        # Add cache control headers to prevent caching
        response = send_file(file_path, mimetype="audio/wav")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    return jsonify({"error": "File not found"}), 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)