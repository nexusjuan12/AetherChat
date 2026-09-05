"""
Entrypoint. The app used to be one 2600+ line file; it's now assembled by
app.create_app() from extension/model/blueprint modules under app/. This
file just builds it and (when run directly) starts the dev server, same as
before.
"""
from app import create_app
from app.media import kobold_handler, tts_handler
from queue_system import setup_queue_handlers

app = create_app()

if __name__ == '__main__':
    setup_queue_handlers(kobold_handler, tts_handler)
    print("Starting app on internal port 8081 (external 51069)...")
    app.run(host='0.0.0.0', port=8081, debug=False)
