import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

DOWNLOAD_FOLDER = "downloads"
RENAME_DELAY = 1.0

class WebmHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith(".webm"):
            time.sleep(RENAME_DELAY)
            old_path = event.src_path
            new_path = old_path[:-5]  # Remove ".webm"
            if not os.path.exists(new_path):
                os.rename(old_path, new_path)
                print(f"✅ Renamed: {os.path.basename(old_path)} -> {os.path.basename(new_path)}")

if __name__ == "__main__":
    print("👀 Watching for new .webm files...")
    observer = Observer()
    observer.schedule(WebmHandler(), path=DOWNLOAD_FOLDER, recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("🛑 停止されました")
    observer.join()
