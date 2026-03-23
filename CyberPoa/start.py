import shutil
import sys
import threading
import webbrowser
from pathlib import Path

from waitress import serve


HOST = "127.0.0.1"
PORT = 8000


def ensure_runtime_files():
    if not getattr(sys, "frozen", False):
        return

    bundle_dir = Path(getattr(sys, "_MEIPASS"))
    app_home = Path(sys.executable).resolve().parent

    bundled_db = bundle_dir / "db.sqlite3"
    runtime_db = app_home / "db.sqlite3"
    if bundled_db.exists() and not runtime_db.exists():
        shutil.copy2(bundled_db, runtime_db)

    (app_home / "media").mkdir(exist_ok=True)


def open_browser():
    webbrowser.open(f"http://{HOST}:{PORT}")


def main():
    ensure_runtime_files()

    from CyberPoa.wsgi import application

    # Open the app shortly after the server starts listening.
    threading.Timer(2, open_browser).start()
    serve(application, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
