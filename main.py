import os
import time
import tempfile
import subprocess
import base64
import hashlib
from discord import app_commands, Intents, Client, Interaction
import discord
import yt_dlp

# === 設定 ===
TOKEN = "YOUR_DISCORD_BOT_TOKEN"
COOLDOWN_SECONDS = 180
MAX_FILE_SIZE_MB = 1024 * 10  # 10 GB（transfer.sh制限）

# === Discord Bot ===
intents = Intents.default()
client = Client(intents=intents)
tree = app_commands.CommandTree(client)
cooldowns = {}
cache = {}  # URL+format : uploaded link

# === ヘルパー ===
def is_on_cooldown(user_id, cmd_key):
    now = time.time()
    last = cooldowns.get(user_id, {}).get(cmd_key, 0)
    if now - last > COOLDOWN_SECONDS:
        cooldowns.setdefault(user_id, {})[cmd_key] = now
        return False
    return True

def generate_id(link):
    return base64.urlsafe_b64encode(hashlib.sha256(link.encode()).digest()[:6]).decode()

def sanitize_filename(name):
    return "".join(c if c.isalnum() or c in "-_()[]" else "_" for c in name)[:100]

def get_title(link):
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(link, download=False)
            return info.get("title", "video")
    except Exception:
        return "video"

def download_and_upload(link, format_opt, is_audio):
    ext = "mp3" if is_audio else "mp4"
    title = sanitize_filename(get_title(link))
    filename = f"{title}.{ext}"

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, filename)

        ydl_opts = {
            'format': format_opt,
            'outtmpl': output_path,
            'quiet': True,
            'noplaylist': True,
            'continuedl': True,
            'retries': 3,
            'no_warnings': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([link])

        if not os.path.exists(output_path):
            raise Exception("ダウンロードに失敗しました")

        # ファイルサイズ制限チェック（transfer.shは10GBまで）
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            raise Exception(f"ファイルサイズが大きすぎます（{size_mb:.2f}MB）")

        result = subprocess.run(
            ["curl", "--upload-file", output_path, f"https://transfer.sh/{filename}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=90
        )

        if result.returncode != 0:
            raise Exception(f"curlエラー: {result.stderr.decode()}")

        return result.stdout.decode().strip()

# === ダウンロード処理 ===
async def handle_download(interaction: Interaction, link: str, fmt: str, is_audio: bool):
    user_id = interaction.user.id
    cmd_key = link + fmt

    if is_on_cooldown(user_id, fmt):
        await interaction.response.send_message("⏳ スパム防止のため3分待ってください。", ephemeral=True)
        return

    if cmd_key in cache:
        await interaction.response.send_message(f"✅ 既にアップ済みです：\n{cache[cmd_key]}", ephemeral=True)
        return

    await interaction.response.send_message("📥 ダウンロード中... しばらくお待ちください。", ephemeral=True)

    try:
        url = download_and_upload(link, fmt, is_audio)
        cache[cmd_key] = url
        await interaction.followup.send(f"✅ 完了！ダウンロードリンク：\n{url}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ エラー発生: {e}", ephemeral=True)

# === コマンド定義 ===
@tree.command(name="videomp4downloader", description="動画をMP4でダウンロード")
@app_commands.describe(link="YouTube動画のURL")
async def videomp4(interaction: Interaction, link: str):
    await handle_download(interaction, link, "bestvideo[ext=mp4]+bestaudio/best", is_audio=False)

@tree.command(name="videomp3downloader", description="動画をMP3でダウンロード")
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
        "**📽️ YouTube ダウンローダーBot 機能一覧**\n"
        "・`/videomp4downloader <url>`：動画を MP4\n"
        "・`/videomp3downloader <url>`：動画を MP3\n"
        "・`/shortmp4downloader <url>`：Shorts を MP4\n"
        "・`/shortmp3downloader <url>`：Shorts 音声を MP3\n"
        "・アップロードは transfer.sh 経由（10GB制限）\n"
        "・キャッシュ対応・3分間クールダウン"
    )
    await interaction.response.send_message(msg, ephemeral=True)

# === 起動 ===
@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Bot 起動完了: {client.user}")

if __name__ == "__main__":
    client.run(TOKEN)
