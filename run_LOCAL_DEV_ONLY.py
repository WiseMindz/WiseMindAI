# WARNING: LOCAL DEV ONLY
# This script is only intended for local development.
# Do not run this file in production or on Railway.
# It watches .py file changes and restarts bot.py automatically.

import subprocess
import time
import sys
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class RestartHandler(FileSystemEventHandler):
    def __init__(self):
        self.process = None

    def on_modified(self, event):
        if event.src_path.endswith((".py",)) and not event.src_path.endswith('run.py'):
            print(f"\n🔄 Fil ändrad: {event.src_path} → Startar om botten...")
            self.restart_bot()

    def restart_bot(self):
        if self.process:
            self.process.kill()
            print("🛑 Gamla botten stoppad")
        
        print("🚀 Startar ny bot...")
        self.process = subprocess.Popen([sys.executable, "bot.py"])


def main():
    event_handler = RestartHandler()
    observer = Observer()
    observer.schedule(event_handler, ".", recursive=False)
    observer.start()

    print("="*60)
    print("👀 WiseMind AI Watchdog AKTIVERAD")
    print("   → Botten startar om automatiskt när du sparar .py filer")
    print("   → Tryck Ctrl+C för att stoppa allt")
    print("="*60)

    event_handler.restart_bot()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Stänger ner...")
        if event_handler.process:
            event_handler.process.kill()
        observer.stop()

if __name__ == "__main__":
    main()
