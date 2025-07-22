import os
import time

DOWNLOAD_FOLDER = "downloads"

def clean_webm_suffix():
    for filename in os.listdir(DOWNLOAD_FOLDER):
        if filename.endswith(".webm"):
            # 例: id.mp4.webm → id.mp4
            new_name = filename[:-5]
            old_path = os.path.join(DOWNLOAD_FOLDER, filename)
            new_path = os.path.join(DOWNLOAD_FOLDER, new_name)
            print(f"Renaming {filename} → {new_name}")
            os.rename(old_path, new_path)

if __name__ == "__main__":
    while True:
        clean_webm_suffix()
        time.sleep(10)  # 10秒ごとに監視
