import os
import threading
from flask import Flask
import bot as bot_module

app = Flask(__name__)


@app.route('/')
def home():
    return "Bot is running"


@app.route('/health')
def health():
    return "OK"


if __name__ == "__main__":
    threading.Thread(target=bot_module.start_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
