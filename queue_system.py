"""Bounded background jobs for inference requests."""
from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class QueuedRequest:
    id: str
    user_id: str
    request_type: str
    data: dict
    created_at: float = field(default_factory=time.time)
    status: str = 'queued'
    result: dict | None = None
    error: str | None = None


class RequestQueue:
    def __init__(self, max_workers: int = 2):
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='aether-job')
        self.handlers: dict[str, Callable[[str, dict], dict]] = {}
        self.requests: dict[str, QueuedRequest] = {}
        self.lock = threading.Lock()

    def register_handler(self, request_type: str, handler: Callable[[str, dict], dict]) -> None:
        self.handlers[request_type] = handler

    def add_request(self, user_id: str, request_type: str, data: dict) -> str:
        if request_type not in self.handlers:
            raise ValueError(f'No handler for {request_type}')
        job = QueuedRequest(id=str(uuid.uuid4()), user_id=user_id, request_type=request_type, data=data)
        with self.lock:
            self.requests[job.id] = job
        self.executor.submit(self._run, job)
        return job.id

    def _run(self, job: QueuedRequest) -> None:
        job.status = 'processing'
        try:
            job.result = self.handlers[job.request_type](job.user_id, job.data)
            job.status = 'complete'
        except Exception as error:
            job.error = str(error)
            job.status = 'error'

    def get_status(self, request_id: str, user_id: str) -> dict | None:
        with self.lock:
            job = self.requests.get(request_id)
        if not job or job.user_id != user_id:
            return None
        payload = {'status': job.status, 'request_id': job.id}
        if job.status == 'complete':
            payload['result'] = job.result
        if job.status == 'error':
            payload['error'] = job.error or 'Generation failed'
        return payload


request_queue = RequestQueue()


def setup_queue_handlers(chat_handler, tts_handler):
    request_queue.register_handler('chat', chat_handler)
    request_queue.register_handler('tts', tts_handler)
