"""
Script di sviluppo per il bot Telegram.
"""

import sys
import time
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class ReloadHandler(FileSystemEventHandler):
    """
    Gestisce il riavvio automatico dello script quando vengono apportate modifiche.
    """

    def __init__(self, script):
        self.script = script
        self.process = None
        self.start_process()

    def start_process(self):
        """
        Avvia il processo dello script.
        """
        if self.process:
            self.process.kill()
        print(f"[DEV] Avvio {self.script}...")
        self.process = subprocess.Popen([sys.executable, self.script])

    def on_modified(self, event):
        if event.src_path.endswith(".py"):
            print("[DEV] Modifica rilevata, riavvio...")
            self.start_process()


if __name__ == "__main__":
    from pathlib import Path
    BASE_DIR = Path(__file__).resolve().parent.parent
    SCRIPT = str(BASE_DIR / "src" / "bot.py")
    event_handler = ReloadHandler(SCRIPT)
    observer = Observer()
    observer.schedule(event_handler, str(BASE_DIR / "src"), recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
