import os
import threading
from flask import Flask
import bot as bot_module

app = Flask(__name__)

# Bot ko background thread me start karne ka function
def run_bot_in_background():
    bot_module.start_bot()

# Bot ko start karo jab app.py load ho
threading.Thread(target=run_bot_in_background, daemon=True).start()

@app.route('/')
def home():
    return "Bot is running properly!"

@app.route('/health')
def health():
    return "OK"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
