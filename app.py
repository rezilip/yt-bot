import threading
from flask import Flask
import bot as bot_module

app = Flask(__name__)


@app.route("/")
def health():
    return "OK - bot is running", 200


def _start_bot_thread():
    t = threading.Thread(target=bot_module.start_polling, daemon=True)
    t.start()


_start_bot_thread()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
