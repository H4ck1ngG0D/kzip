import os, time, threading, base64, hashlib
from flask import Flask, render_template, send_file, abort
from discord import app_commands, Intents, Client, Interaction
import yt_dlp
import discord

# === 環境設定 ===
TOKEN = ""
BASE_URL = "https://ec5a407eeded-5005-shironekousercontent.paicha.dev:5005"
PORT = 5000
DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# === Flask サーバー ===
app = Flask(__name__)
download_info = {}  # id: {path, expire, title, thumbnail}

@app.route("/video/<id>")
def video_page(id):
    info = download_info.get(id)
    if not info or time.time() > info["expire"]:
        return abort(404)
    return render_template("download.html", id=id, title=info.get("title"), thumbnail=info.get("thumbnail"))

@app.route("/download/<id>")
def download_file(id):
    info = download_info.get(id)
    if not info:
        return render_template("download.html", error="指定されたIDは存在しません。")

    if time.time() > info["expire"]:
        return render_template("download.html", error="このダウンロードリンクは有効期限が切れています。")

    exts = ["mp4", "webm", "mp3", "m4a"]
    original_path = info["path"]

    # まずは元のパスで存在チェック
    if os.path.exists(original_path):
        return send_file(original_path, as_attachment=True)

    # 拡張子違いのファイルを探す
    base = os.path.splitext(original_path)[0]
    for ext in exts:
        alt_path = f"{base}.{ext}"
        if os.path.exists(alt_path):
            return send_file(alt_path, as_attachment=True)

    # ファイルが見つからなかった場合はダウンロードページにエラーを渡して表示
    return render_template("download.html", error="ファイルが見つかりませんでした。")

def cleanup_file(id):
    info = download_info.pop(id, None)
    if info:
        try:
            os.remove(info["path"])
        except:
            pass

# === Discord Bot 設定 ===
intents = Intents.default()
client = Client(intents=intents)
tree = app_commands.CommandTree(client)
cooldowns = {}  # user_id: {cmd: last_time}

def is_on_cooldown(user_id, cmd_key):
    now = time.time()
    if user_id not in cooldowns:
        cooldowns[user_id] = {}
    last = cooldowns[user_id].get(cmd_key, 0)
    if now - last > 180:
        cooldowns[user_id][cmd_key] = now
        return False
    return True

def generate_id(link):
    h = hashlib.sha256(link.encode()).digest()
    return base64.urlsafe_b64encode(h[:6]).decode("utf-8")

def extract_info(link, ydl_opts):
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(link, download=False)

def download_video(link, output_path, format_opt):
    ydl_opts = {
        'format': format_opt,
        'outtmpl': output_path,
        'quiet': True,
        'noplaylist': True,
        'continuedl': True,
        'retries': 3,
        'no_warnings': True,
        'concurrent_fragment_downloads': 3,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([link])

async def handle_download(interaction: Interaction, link: str, fmt: str, is_audio: bool):
    user_id = interaction.user.id
    cmd_key = fmt
    if is_on_cooldown(user_id, cmd_key):
        await interaction.response.send_message("⏳ スパム防止のため、3分待ってください。", ephemeral=True)
        return

    await interaction.response.send_message("📥 ダウンロード準備中...", ephemeral=True)
    id = generate_id(link + fmt)
    ext = "mp3" if is_audio else "mp4"
    output_path = os.path.join(DOWNLOAD_FOLDER, f"{id}.{ext}")

    if not os.path.exists(output_path):
        try:
            download_video(link, output_path, fmt)
        except Exception as e:
            await interaction.followup.send(f"❌ ダウンロード失敗: {e}", ephemeral=True)
            return

    info = extract_info(link, {'quiet': True})
    title = info.get("title", "Untitled")
    thumbnail = info.get("thumbnail")

    download_info[id] = {
        'path': output_path,
        'expire': time.time() + 3600,
        'title': title,
        'thumbnail': thumbnail
    }
    threading.Timer(3600, cleanup_file, args=(id,)).start()

    url = f"{BASE_URL}/video/{id}"
    await interaction.followup.send(f"✅ ダウンロード完了！\n[こちらからダウンロード]({url})", ephemeral=True)

# === コマンド登録 ===
@tree.command(name="videomp4downloader", description="通常動画をMP4でダウンロード")
@app_commands.describe(link="YouTube動画のURL")
async def videomp4(interaction: Interaction, link: str):
    await handle_download(interaction, link, "bestvideo[ext=mp4]+bestaudio/best", is_audio=False)

@tree.command(name="videomp3downloader", description="通常動画の音声をMP3でダウンロード")
@app_commands.describe(link="YouTube動画のURL")
async def videomp3(interaction: Interaction, link: str):
    await handle_download(interaction, link, "bestaudio/best", is_audio=True)

@tree.command(name="shortmp4downloader", description="ShortsをMP4でダウンロード")
@app_commands.describe(link="YouTube ShortsのURL")
async def shortmp4(interaction: Interaction, link: str):
    await handle_download(interaction, link, "bestvideo[ext=mp4]+bestaudio/best", is_audio=False)

@tree.command(name="shortmp3downloader", description="Shorts音声をMP3でダウンロード")
@app_commands.describe(link="YouTube ShortsのURL")
async def shortmp3(interaction: Interaction, link: str):
    await handle_download(interaction, link, "bestaudio/best", is_audio=True)

@tree.command(name="botinfo", description="Botの機能一覧を表示")
async def botinfo(interaction: Interaction):
    msg = (
        "**📽️ YouTubeダウンローダーBot機能一覧**\n"
        "・`/videomp4downloader <link>`：通常動画(mp4)\n"
        "・`/videomp3downloader <link>`：通常音声(mp3)\n"
        "・`/shortmp4downloader <link>`：Shorts(mp4)\n"
        "・`/shortmp3downloader <link>`：Shorts音声(mp3)\n"
        "・全コマンド 3分クールダウン付き\n"
        "・動画ページにサムネ・タイトル付きダウンロードボタン"
    )
    await interaction.response.send_message(msg, ephemeral=True)

# === 起動イベント ===
@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Bot起動完了: {client.user}")

# === Flask 起動 ===
def run_flask():
    app.run(host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    client.run(TOKEN)
