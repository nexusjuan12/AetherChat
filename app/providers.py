"""Private HTTP clients for chat and speech inference providers."""
from __future__ import annotations

import base64
import mimetypes
import os
import time
import uuid
from pathlib import Path

import requests

import config


class ProviderError(RuntimeError):
    pass


class AcceleratorBusy(ProviderError):
    pass


class LlmClient:
    def complete(self, payload: dict) -> dict:
        headers = {'content-type': 'application/json'}
        if config.LLM_API_KEY:
            headers['authorization'] = f'Bearer {config.LLM_API_KEY}'
        try:
            response = requests.post(
                f'{config.LLM_API_BASE}/v1/chat/completions', json=payload,
                headers=headers, timeout=(5, 180),
            )
        except requests.RequestException as error:
            raise ProviderError('Text engine is unavailable') from error
        if not response.ok:
            raise ProviderError('Text engine rejected the request')
        return response.json()


class SpeechClient:
    """OpenAI-style TTS adapter with optional P100 accelerator arbitration."""

    def __init__(self):
        self.lease_id: str | None = None

    def _controller_request(self, path: str, payload: dict) -> dict:
        try:
            response = requests.post(
                f'{config.TTS_ACCELERATOR_CONTROLLER_URL}{path}', json=payload,
                timeout=(5, 30),
            )
        except requests.RequestException as error:
            raise ProviderError('Speech accelerator controller is unavailable') from error
        if response.status_code == 409:
            raise AcceleratorBusy('Speech is temporarily unavailable while the image engine is active')
        if not response.ok:
            raise ProviderError('Speech accelerator could not prepare the engine')
        return response.json()

    def acquire(self) -> None:
        if config.TTS_ACCELERATOR_CONTROLLER_URL:
            self.lease_id = self._controller_request('/v1/acquire', {'engine': 'tts'})['leaseId']

    def release(self) -> None:
        if self.lease_id and config.TTS_ACCELERATOR_CONTROLLER_URL:
            try:
                self._controller_request('/v1/release', {'leaseId': self.lease_id})
            finally:
                self.lease_id = None

    def prepare_voice_profile(self, sample_path: Path, reference_text: str, display_name: str) -> str:
        """Ask the provider to retain/cache a reference without exposing it to clients."""
        headers = {}
        if config.TTS_API_KEY:
            headers['authorization'] = f'Bearer {config.TTS_API_KEY}'
        try:
            with sample_path.open('rb') as sample:
                content_type = mimetypes.guess_type(sample_path.name)[0] or 'application/octet-stream'
                response = requests.post(
                    f'{config.TTS_API_BASE}/v1/voices', headers=headers,
                    files={'sample': (sample_path.name, sample, content_type)},
                    data={'reference_text': reference_text, 'display_name': display_name},
                    timeout=(10, 300),
                )
        except requests.RequestException as error:
            raise ProviderError('Speech provider is unavailable') from error
        if not response.ok:
            raise ProviderError('Speech provider could not prepare this voice profile')
        data = response.json()
        profile_id = data.get('id') or data.get('voice_profile_id')
        if not profile_id:
            raise ProviderError('Speech provider returned an invalid voice profile')
        return str(profile_id)

    def delete_voice_profile(self, provider_profile_id: str) -> None:
        """Remove a provider-side voice profile after the owner deletes it."""
        headers = {}
        if config.TTS_API_KEY:
            headers['authorization'] = f'Bearer {config.TTS_API_KEY}'
        try:
            response = requests.delete(
                f'{config.TTS_API_BASE}/v1/voices/{provider_profile_id}',
                headers=headers, timeout=(5, 30),
            )
        except requests.RequestException as error:
            raise ProviderError('Speech provider is unavailable') from error
        if response.status_code not in {204, 404}:
            raise ProviderError('Speech provider could not remove this voice profile')

    def synthesize(self, text: str, voice_profile_id: str | None) -> bytes:
        headers = {'content-type': 'application/json'}
        if config.TTS_API_KEY:
            headers['authorization'] = f'Bearer {config.TTS_API_KEY}'
        payload = {
            'model': 'qwen-tts',
            'input': text,
            'voice': voice_profile_id or config.TTS_DEFAULT_VOICE,
            'response_format': 'wav',
        }
        self.acquire()
        try:
            response = requests.post(
                f'{config.TTS_API_BASE}/v1/audio/speech', json=payload,
                headers=headers, timeout=(10, 300),
            )
        except requests.RequestException as error:
            raise ProviderError('Speech engine is unavailable') from error
        finally:
            self.release()
        if not response.ok or len(response.content) < 44:
            raise ProviderError('Speech engine did not produce usable audio')
        return response.content


def write_owned_audio(user_id: str, audio: bytes) -> tuple[str, Path]:
    filename = f'{user_id}-{uuid.uuid4()}.wav'
    path = Path(config.OUTPUT_DIR) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audio)
    return filename, path
