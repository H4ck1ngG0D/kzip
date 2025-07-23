import os
import time

DOWNLOAD_FOLDER = "downloads"
RENAME_DELAY = 1.0  # ファイル生成から1秒後にリネーム

def clean_webm_suffix():
    now = time.time()
    for filename in os.listdir(DOWNLOAD_FOLDER):
        if filename.endswith(".webm"):
            path = os.path.join(DOWNLOAD_FOLDER, filename)
            if now - os.path.getmtime(path) >= RENAME_DELAY:
                new_name = filename[:-5]  # ".webm" を取り除く
                new_path = os.path.join(DOWNLOAD_FOLDER, new_name)
                if not os.path.exists(new_path):  # 上書き防止
                    os.rename(path, new_path)
                    print(f"✅ Renamed: {filename} -> {new_name}")

if __name__ == "__main__":
    time.sleep(1)  # 初回起動時に少し待つ（必要なら）
    clean_webm_suffix()
