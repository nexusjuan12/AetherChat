# model_cache.py
import os
import time
import uuid
from threading import Lock, Timer
import weakref
from tts_with_rvc import TTS_RVC

class RVCModelCache:
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, cache_timeout=1800, base_model_path="/root/models", input_dir="/root/input/", output_dir="/root/output/"):
        # Only initialize if this is the first time
        if not hasattr(self, '_initialized'):
            self._cache = {}
            self._last_used = {}
            self._locks = {}
            self._timers = {}
            self._cache_timeout = cache_timeout
            self._global_lock = Lock()
            self._base_model_path = base_model_path
            self._input_dir = input_dir
            self._output_dir = output_dir
            self._initialized = True
            print("RVC Model Cache initialized with priority queue support")

    def get_model(self, character_id, edge_voice=None):
        """Get a cached TTS_RVC model or create a new one"""
        with self._global_lock:
            if character_id not in self._locks:
                self._locks[character_id] = Lock()

        with self._locks[character_id]:
            current_time = time.time()
            
            # Return existing model if cached
            if character_id in self._cache:
                print(f"Using cached model for character {character_id}")
                self._last_used[character_id] = current_time
                
                # Reset cleanup timer
                if character_id in self._timers:
                    self._timers[character_id].cancel()
                self._timers[character_id] = Timer(
                    self._cache_timeout, 
                    self._cleanup_model, 
                    args=[character_id]
                )
                self._timers[character_id].start()
                
                model = self._cache[character_id]
                if edge_voice:
                    model.set_voice(edge_voice)
                return model

            # Create new model instance
            try:
                model_path = os.path.join(self._base_model_path, character_id, f"{character_id}.pth")
                index_path = os.path.join(self._base_model_path, character_id, f"{character_id}.index")

                if not os.path.exists(model_path):
                    raise FileNotFoundError(f"Model file not found: {model_path}")
                if not os.path.exists(index_path):
                    raise FileNotFoundError(f"Index file not found: {index_path}")

                print(f"Creating new TTS_RVC instance for character {character_id}")
                tts_instance = TTS_RVC(
                    rvc_path="src/rvclib",
                    model_path=model_path,
                    input_directory=self._input_dir,
                    index_path=index_path
                )
                
                if edge_voice:
                    tts_instance.set_voice(edge_voice)

                # Store with weak reference
                
                self._cache[character_id] = tts_instance
                self._last_used[character_id] = current_time
                
                # Set cleanup timer
                self._timers[character_id] = Timer(
                    self._cache_timeout, 
                    self._cleanup_model, 
                    args=[character_id]
                )
                self._timers[character_id].start()
                
                return tts_instance

            except Exception as e:
                print(f"Error creating TTS_RVC instance for {character_id}: {str(e)}")
                raise

    def handle_queued_request(self, data):
        """Handler function for queue system"""
        try:
            text = data.get("text")
            character_id = data.get("rvc_model")
            edge_voice = data.get("edge_voice")
            tts_rate = data.get("tts_rate", 0)
            rvc_pitch = data.get("rvc_pitch", 0)

            # Get or create model instance
            tts = self.get_model(character_id, edge_voice)
            
            # Generate unique filename
            unique_id = str(uuid.uuid4())
            output_filename = f"response_{unique_id}.wav"
            output_path = os.path.join(self._output_dir, output_filename)

            print(f"Generating audio for queued request (character: {character_id})")
            tts(
                text=text,
                pitch=rvc_pitch,
                tts_rate=tts_rate,
                output_filename=output_path
            )

            if not os.path.exists(output_path):
                raise Exception("Failed to generate audio file")

            return {"audio_url": f"/audio/{output_filename}"}

        except Exception as e:
            print(f"Queue request processing error: {str(e)}")
            import traceback
            traceback.print_exc()
            raise

    def _cleanup_model(self, character_id):
        """Clean up an unused model"""
        with self._locks[character_id]:
            if character_id in self._cache:
                print(f"Cleaning up unused model for character {character_id}")
                del self._cache[character_id]
                del self._last_used[character_id]
                if character_id in self._timers:
                    self._timers[character_id].cancel()
                    del self._timers[character_id]

    def clear_cache(self):
        """Clear all cached models"""
        with self._global_lock:
            for character_id in list(self._cache.keys()):
                self._cleanup_model(character_id)

    def get_cache_stats(self):
        """Get current cache statistics"""
        with self._global_lock:
            return {
                'cached_models': len(self._cache),
                'models': list(self._cache.keys()),
                'last_used': {k: time.ctime(v) for k, v in self._last_used.items()}
            }

# Create global instance
model_cache = RVCModelCache()

# Queue handler function for TTS
def tts_handler(data):
    """TTS handler function for queue system"""
    return model_cache.handle_queued_request(data)