from collections import deque
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional, Callable
import uuid

@dataclass
class QueuedRequest:
    id: str
    user_id: str
    request_type: str  # 'chat' or 'tts'
    data: dict
    timestamp: float
    status: str = 'pending'
    result: Optional[dict] = None
    position: int = 0

class RequestQueue:
    def __init__(self, max_concurrent: int = 5):
        self.chat_queue = deque()
        self.tts_queue = deque()
        self.processing = {}  # Currently processing requests
        self.max_concurrent = max_concurrent
        self.lock = threading.Lock()
        self.processing_thread = threading.Thread(target=self._process_queues, daemon=True)
        self.processing_thread.start()
        
        # Handlers for different request types
        self.handlers = {
            'chat': None,
            'tts': None
        }

    def add_request(self, user_id: str, request_type: str, data: dict) -> str:
        """Add a new request to the appropriate queue."""
        with self.lock:
            request_id = str(uuid.uuid4())
            request = QueuedRequest(
                id=request_id,
                user_id=user_id,
                request_type=request_type,
                data=data,
                timestamp=time.time()
            )
            
            queue = self.tts_queue if request_type == 'tts' else self.chat_queue
            queue.append(request)
            self._update_positions(queue)
            
            return request_id

    def get_status(self, request_id: str) -> Optional[dict]:
        """Get the current status of a request."""
        # Check processing requests first
        if request_id in self.processing:
            request = self.processing[request_id]
            return {
                'status': request.status,
                'position': 0,
                'result': request.result
            }
            
        # Check queues
        for queue in [self.chat_queue, self.tts_queue]:
            for request in queue:
                if request.id == request_id:
                    return {
                        'status': 'queued',
                        'position': request.position
                    }
                    
        return None

    def register_handler(self, request_type: str, handler: Callable):
        """Register a handler function for a specific request type."""
        self.handlers[request_type] = handler

    def _update_positions(self, queue: deque):
        """Update position numbers in queue."""
        for i, request in enumerate(queue):
            request.position = i + 1

    def _process_queues(self):
        """Main processing loop for queued requests."""
        while True:
            try:
                with self.lock:
                    # Process priority queue (TTS) first
                    if self.tts_queue and len(self.processing) < self.max_concurrent:
                        request = self.tts_queue.popleft()
                        self._process_request(request)
                        self._update_positions(self.tts_queue)
                        
                    # Then process chat queue
                    elif self.chat_queue and len(self.processing) < self.max_concurrent:
                        request = self.chat_queue.popleft()
                        self._process_request(request)
                        self._update_positions(self.chat_queue)

                time.sleep(0.1)  # Prevent CPU spinning
                
            except Exception as e:
                print(f"Error in queue processing: {e}")
                time.sleep(1)  # Back off on error

    def _process_request(self, request: QueuedRequest):
        """Process a single request."""
        handler = self.handlers.get(request.request_type)
        if not handler:
            request.status = 'error'
            request.result = {'error': f'No handler for {request.request_type}'}
            return

        try:
            self.processing[request.id] = request
            request.status = 'processing'
            
            # Process the request
            result = handler(request.data)
            request.result = result
            request.status = 'complete'
            
        except Exception as e:
            request.status = 'error'
            request.result = {'error': str(e)}
            
        finally:
            # Keep completed requests in processing dict for a short time
            # for status checks, then clean up
            def cleanup():
                time.sleep(30)  # Keep result for 30 seconds
                with self.lock:
                    self.processing.pop(request.id, None)
                    
            threading.Thread(target=cleanup, daemon=True).start()

# Initialize global queue
request_queue = RequestQueue(max_concurrent=5)

# Example route handlers
def handle_chat_request(app):
    @app.route('/v1/chat/completions', methods=['POST'])
    @login_required
    def chat_completions():
        try:
            data = request.json
            user_id = current_user.id
            
            # Add to queue and get request ID
            request_id = request_queue.add_request(user_id, 'chat', data)
            
            # Check if request can be processed immediately
            status = request_queue.get_status(request_id)
            
            if status['status'] == 'queued' and status['position'] > 3:
                # Return queued status if position is high
                return jsonify({
                    'status': 'queued',
                    'position': status['position'],
                    'request_id': request_id
                })
            
            # Poll for completion if position is low
            for _ in range(30):  # 30 second timeout
                status = request_queue.get_status(request_id)
                if status['status'] == 'complete':
                    return jsonify(status['result'])
                elif status['status'] == 'error':
                    return jsonify({'error': status['result']['error']}), 500
                time.sleep(1)
            
            return jsonify({'error': 'Request timeout'}), 408
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/v1/chat/status/<request_id>')
    @login_required
    def check_chat_status(request_id):
        status = request_queue.get_status(request_id)
        if not status:
            return jsonify({'error': 'Request not found'}), 404
        return jsonify(status)

# Register handlers
def setup_queue_handlers(kobold_handler, tts_handler):
    request_queue.register_handler('chat', kobold_handler)
    request_queue.register_handler('tts', tts_handler)