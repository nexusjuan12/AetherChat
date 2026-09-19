# AetherChat

Invite-only character chat built around private, OpenAI-compatible text and speech providers. The application never runs a model in its web process and browser clients never receive provider credentials.

## Current scope

- Local invite-only accounts with administrator-assisted recovery.
- Optional Authentik identity mapping for a trusted reverse-proxy deployment.
- Character chat via a private `/v1/chat/completions` provider.
- Optional speech via a private `/v1/audio/speech` provider.
- Character ownership, private/public approval workflow, and media uploads.
- Per-user queued text/speech requests.
- Qwen voice-profile data model and approval policy.

Story Mode is intentionally disabled pending repair. Video is represented only as a deployment-level feature flag; this repository does not deploy a video service. Payments, Google authentication, RVC, Stripe, and browser-to-model access are intentionally absent.

## Quick start

```bash
cp .env.example .env
python3 manage.py new-secret
# set SECRET_KEY in .env, then set SESSION_COOKIE_SECURE=false for local HTTP development
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3 manage.py bootstrap-admin --username admin --email admin@example.test
python3 webserver.py
```

Open `http://127.0.0.1:8081`. Create invitations through `POST /api/admin/invites` as an administrator. Local recovery is administrator-assisted; no email delivery service is included.

For container use:

```bash
cp .env.example .env
mkdir -p data
docker compose up --build -d
```

The compose file binds the service to loopback only. Put it behind an HTTPS reverse proxy for a real deployment.

## Provider contracts

Set `LLM_API_BASE` to an OpenAI-compatible server exposing:

```text
POST /v1/chat/completions
```

Set `TTS_API_BASE` to a private OpenAI-compatible speech service exposing:

```text
POST /v1/audio/speech
```

The app sends a Qwen-oriented request with `model`, `input`, `voice`, and `response_format: wav`. Configure `TTS_ACCELERATOR_CONTROLLER_URL` only when speech must acquire a shared GPU lease before use.

### Voice profiles

The application accepts a consented audio sample, transcript, visibility choice, and review state. Private profiles are owner-only; public profiles require administrator approval. Activating a profile additionally requires the TTS provider to support:

```text
POST /v1/voices (multipart: sample, reference_text, display_name)
```

and return an `id` or `voice_profile_id` that can be supplied to `/v1/audio/speech`. The current generic interface does not invent a provider-specific cloning implementation. Until the Qwen TTS endpoint exposes this contract, profile enrollment returns a clear provider error instead of storing an unusable clone.

## Bizarre Labs deployment

Use `AUTH_MODE=authentik` only behind Caddy (or another trusted proxy) that strips client-supplied identity headers and sets:

```text
X-Authentik-Uid
X-Authentik-Username
X-Authentik-Email
X-Authentik-Groups
```

Set `TRUST_AUTHENTIK_HEADERS=true` and `AUTHENTIK_REQUIRED_GROUPS=members` (or the chosen member group). The Authentik UID is the stable account mapping key; the Lounge handle is the display/login name. The public/local invite flow stays separate.

Provider endpoints must be reachable only from the server network. Do not set their URLs in browser JavaScript or expose their tunnel ports publicly.

## Runtime data and backup

Production runtime state belongs outside the Git checkout:

- SQLite database (`DB_PATH`)
- generated audio (`OUTPUT_DIR`)
- private voice samples (`VOICE_SAMPLE_DIR`)
- uploaded avatar/background media if custom paths are used

Back up those paths and `.env` separately. Do not commit database files, sample audio, generated outputs, passwords, API keys, or tunnel credentials.

## Development notes

`webserver.py` is the development entrypoint. Gunicorn works because queue handlers are registered in `app.create_app()`, not only in the development process.

Run a syntax/smoke check with:

```bash
python3 -m compileall -q app webserver.py manage.py queue_system.py
```

## Repository relationship

`AetherChat` is the reusable public core. `AetherChatV3` remains the separate experimental video/billing line. Shared core-only changes should be carried across deliberately; generated video artifacts and deployment-specific configuration must not be copied into this repository.
