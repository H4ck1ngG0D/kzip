import os, time, threading, base64, hashlib, re
from flask import Flask, render_template, send_file, abort, jsonify
from discord import app_commands, Intents, Client, Interaction
import yt_dlp
import discord
from urllib.parse import urlparse
import logging

# === ログ設定 ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === 環境設定 ===
TOKEN = os.getenv("DISCORD_TOKEN", "")  # 環境変数から取得
BASE_URL = os.getenv("BASE_URL", "https://ec5a407eeded-5005-shironekousercontent.paicha.dev:5005")
PORT = int(os.getenv("PORT", 5000))
DOWNLOAD_FOLDER = "downloads"
TEMP_FOLDER = "temp"

# フォルダ作成
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(TEMP_FOLDER, exist_ok=True)

# === Flask サーバー ===
app = Flask(__name__)
download_info = {}  # id: {path, expire, title, thumbnail, original_filename}

def is_valid_youtube_url(url):
    """YouTube URLの妥当性チェック"""
    youtube_patterns = [
        r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=[\w-]+',
        r'(?:https?://)?(?:www\.)?youtube\.com/shorts/[\w-]+',
        r'(?:https?://)?youtu\.be/[\w-]+',
        r'(?:https?://)?(?:m\.)?youtube\.com/watch\?v=[\w-]+',
    ]
    return any(re.match(pattern, url) for pattern in youtube_patterns)

def sanitize_filename(filename):
    """ファイル名を安全にする"""
    # 危険な文字を除去
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # 長すぎる場合は切り詰め
    if len(filename) > 100:
        filename = filename[:100]
    return filename.strip()

def get_safe_filename(info, file_id, is_audio=False):
    """安全なファイル名を生成"""
    title = info.get('title', 'video')
    title = sanitize_filename(title)
    ext = 'mp3' if is_audio else 'mp4'
    return f"{file_id}_{title}.{ext}"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/video/<id>")
def video_page(id):
    info = download_info.get(id)
    if not info or time.time() > info["expire"]:
        return render_template("error.html", error="指定されたIDは存在しないか、有効期限が切れています。")
    
    return render_template("download.html", 
                         id=id, 
                         title=info.get("title", "Unknown"),
                         thumbnail=info.get("thumbnail"),
                         original_filename=info.get("original_filename", "video"))

@app.route("/download/<id>")
def download_file(id):
    info = download_info.get(id)
    if not info:
        return render_template("error.html", error="指定されたIDは存在しません。")

    if time.time() > info["expire"]:
        return render_template("error.html", error="このダウンロードリンクは有効期限が切れています。")

    file_path = info["path"]
    original_filename = info.get("original_filename", "video.mp4")
    
    # ファイル存在確認
    if not os.path.exists(file_path):
        # 拡張子違いのファイルを探す
        base_path = os.path.splitext(file_path)[0]
        extensions = ["mp4", "webm", "mp3", "m4a", "mkv", "avi"]
        
        found_file = None
        for ext in extensions:
            alt_path = f"{base_path}.{ext}"
            if os.path.exists(alt_path):
                found_file = alt_path
                # 元のファイル名の拡張子も更新
                base_name = os.path.splitext(original_filename)[0]
                original_filename = f"{base_name}.{ext}"
                break
        
        if not found_file:
            return render_template("error.html", error="ファイルが見つかりませんでした。")
        
        file_path = found_file

    try:
        return send_file(file_path, 
                        as_attachment=True, 
                        download_name=original_filename,
                        mimetype='application/octet-stream')
    except Exception as e:
        logger.error(f"ファイル送信エラー: {e}")
        return render_template("error.html", error="ファイルの送信中にエラーが発生しました。")

@app.route("/api/status/<id>")
def check_status(id):
    """ダウンロード状況をAPIで確認"""
    info = download_info.get(id)
    if not info:
        return jsonify({"status": "not_found"})
    
    if time.time() > info["expire"]:
        return jsonify({"status": "expired"})
    
    if os.path.exists(info["path"]):
        return jsonify({"status": "ready", "title": info.get("title")})
    
    return jsonify({"status": "processing"})

def cleanup_file(id):
    """ファイルクリーンアップ"""
    info = download_info.pop(id, None)
    if info:
        try:
            if os.path.exists(info["path"]):
                os.remove(info["path"])
                logger.info(f"ファイル削除完了: {info['path']}")
        except Exception as e:
            logger.error(f"ファイル削除エラー: {e}")

def cleanup_old_files():
    """古いファイルの定期クリーンアップ"""
    try:
        current_time = time.time()
        for folder in [DOWNLOAD_FOLDER, TEMP_FOLDER]:
            for filename in os.listdir(folder):
                filepath = os.path.join(folder, filename)
                if os.path.isfile(filepath):
                    # 2時間以上古いファイルを削除
                    if current_time - os.path.getctime(filepath) > 7200:
                        os.remove(filepath)
                        logger.info(f"古いファイルを削除: {filepath}")
    except Exception as e:
        logger.error(f"クリーンアップエラー: {e}")

# 定期クリーンアップを1時間ごとに実行
def schedule_cleanup():
    cleanup_old_files()
    threading.Timer(3600, schedule_cleanup).start()

# === Discord Bot 設定 ===
intents = Intents.default()
client = Client(intents=intents)
tree = app_commands.CommandTree(client)
cooldowns = {}  # user_id: {cmd: last_time}

def is_on_cooldown(user_id, cmd_key, cooldown_seconds=180):
    """クールダウンチェック"""
    now = time.time()
    if user_id not in cooldowns:
        cooldowns[user_id] = {}
    last = cooldowns[user_id].get(cmd_key, 0)
    if now - last > cooldown_seconds:
        cooldowns[user_id][cmd_key] = now
        return False
    return True

def generate_id(link, fmt):
    """ユニークIDを生成"""
    content = f"{link}_{fmt}_{int(time.time())}"
    h = hashlib.sha256(content.encode()).digest()
    return base64.urlsafe_b64encode(h[:8]).decode("utf-8").rstrip('=')

def extract_info_safe(link):
    """安全に動画情報を取得"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'skip_download': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(link, download=False)
    except Exception as e:
        logger.error(f"動画情報取得エラー: {e}")
        return None

def download_video_safe(link, output_path, format_opt, is_audio=False):
    """安全にダウンロード実行"""
    # 一時ファイルパスを生成
    temp_path = os.path.join(TEMP_FOLDER, f"temp_{os.path.basename(output_path)}")
    
    ydl_opts = {
        'format': format_opt,
        'outtmpl': temp_path,
        'quiet': True,
        'no_warnings': True,
        'continuedl': True,
        'retries': 3,
        'fragment_retries': 3,
        'concurrent_fragment_downloads': 2,
        'writeinfojson': False,
        'writesubtitles': False,
        'writeautomaticsub': False,
    }
    
    # 音声の場合の追加設定
    if is_audio:
        ydl_opts.update({
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([link])
        
        # 実際に作成されたファイルを探す
        base_temp = os.path.splitext(temp_path)[0]
        possible_extensions = ['mp4', 'webm', 'mp3', 'm4a', 'mkv'] if not is_audio else ['mp3', 'm4a']
        
        actual_file = None
        for ext in possible_extensions:
            test_path = f"{base_temp}.{ext}"
            if os.path.exists(test_path):
                actual_file = test_path
                break
        
        if not actual_file:
            # 元のパスをチェック
            if os.path.exists(temp_path):
                actual_file = temp_path
        
        if actual_file and os.path.exists(actual_file):
            # 最終的な出力パスに移動
            final_ext = os.path.splitext(actual_file)[1]
            final_output = os.path.splitext(output_path)[0] + final_ext
            os.rename(actual_file, final_output)
            return final_output
        else:
            raise Exception("ダウンロードされたファイルが見つかりません")
            
    except Exception as e:
        # 一時ファイルのクリーンアップ
        for ext in ['mp4', 'webm', 'mp3', 'm4a', 'mkv']:
            test_path = f"{base_temp}.{ext}"
            if os.path.exists(test_path):
                try:
                    os.remove(test_path)
                except:
                    pass
        raise e

async def handle_download(interaction: Interaction, link: str, fmt: str, is_audio: bool):
    """ダウンロード処理のメインハンドラー"""
    user_id = interaction.user.id
    cmd_key = "audio" if is_audio else "video"
    
    # URL妥当性チェック
    if not is_valid_youtube_url(link):
        await interaction.response.send_message("❌ 有効なYouTube URLを入力してください。", ephemeral=True)
        return
    
    # クールダウンチェック
    if is_on_cooldown(user_id, cmd_key):
        await interaction.response.send_message("⏳ スパム防止のため、3分待ってください。", ephemeral=True)
        return

    await interaction.response.send_message("📥 動画情報を取得中...", ephemeral=True)
    
    # 動画情報取得
    info = extract_info_safe(link)
    if not info:
        await interaction.followup.send("❌ 動画情報を取得できませんでした。URLを確認してください。", ephemeral=True)
        return
    
    # ID生成とファイルパス設定
    file_id = generate_id(link, fmt)
    title = info.get("title", "Unknown Video")
    safe_filename = get_safe_filename(info, file_id, is_audio)
    output_path = os.path.join(DOWNLOAD_FOLDER, safe_filename)
    
    await interaction.followup.send(f"📥 ダウンロード開始: {title[:50]}...", ephemeral=True)
    
    try:
        # ダウンロード実行
        final_path = download_video_safe(link, output_path, fmt, is_audio)
        
        # ダウンロード情報を保存
        download_info[file_id] = {
            'path': final_path,
            'expire': time.time() + 3600,  # 1時間後に期限切れ
            'title': title,
            'thumbnail': info.get("thumbnail"),
            'original_filename': os.path.basename(final_path)
        }
        
        # 1時間後にクリーンアップをスケジュール
        threading.Timer(3600, cleanup_file, args=(file_id,)).start()
        
        # 成功メッセージ
        download_url = f"{BASE_URL}/video/{file_id}"
        await interaction.followup.send(
            f"✅ **ダウンロード完了！**\n"
            f"📹 {title[:100]}\n"
            f"🔗 [ダウンロードページ]({download_url})\n"
            f"⏰ 有効期限: 1時間", 
            ephemeral=True
        )
        
    except Exception as e:
        logger.error(f"ダウンロードエラー: {e}")
        await interaction.followup.send(f"❌ ダウンロードに失敗しました: {str(e)[:100]}", ephemeral=True)

# === Discord コマンド ===
@tree.command(name="videomp4", description="YouTube動画をMP4でダウンロード")
@app_commands.describe(link="YouTube動画のURL")
async def videomp4(interaction: Interaction, link: str):
    await handle_download(interaction, link, "best[ext=mp4]/best", is_audio=False)

@tree.command(name="videomp3", description="YouTube動画の音声をMP3でダウンロード")
@app_commands.describe(link="YouTube動画のURL")
async def videomp3(interaction: Interaction, link: str):
    await handle_download(interaction, link, "bestaudio/best", is_audio=True)

@tree.command(name="shortmp4", description="YouTube ShortsをMP4でダウンロード")
@app_commands.describe(link="YouTube ShortsのURL")
async def shortmp4(interaction: Interaction, link: str):
    await handle_download(interaction, link, "best[ext=mp4]/best", is_audio=False)

@tree.command(name="shortmp3", description="YouTube Shortsの音声をMP3でダウンロード")
@app_commands.describe(link="YouTube ShortsのURL")
async def shortmp3(interaction: Interaction, link: str):
    await handle_download(interaction, link, "bestaudio/best", is_audio=True)

@tree.command(name="help", description="使用方法とBot情報を表示")
async def help_command(interaction: Interaction):
    embed = discord.Embed(
        title="📽️ YouTube ダウンローダー Bot",
        description="高性能なYouTube動画ダウンローダー",
        color=0x00ff00
    )
    embed.add_field(
        name="📹 動画コマンド",
        value="• `/videomp4 <URL>` - 通常動画(MP4)\n• `/shortmp4 <URL>` - Shorts(MP4)",
        inline=False
    )
    embed.add_field(
        name="🎵 音声コマンド", 
        value="• `/videomp3 <URL>` - 通常音声(MP3)\n• `/shortmp3 <URL>` - Shorts音声(MP3)",
        inline=False
    )
    embed.add_field(
        name="⚙️ 仕様",
        value="• 3分間のクールダウン\n• 1時間のダウンロード有効期限\n• 自動ファイル名最適化",
        inline=False
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

# === Bot イベント ===
@client.event
async def on_ready():
    try:
        synced = await tree.sync()
        logger.info(f"✅ Bot起動完了: {client.user} | {len(synced)}個のコマンドを同期")
        schedule_cleanup()  # 定期クリーンアップ開始
    except Exception as e:
        logger.error(f"コマンド同期エラー: {e}")

@client.event
async def on_command_error(ctx, error):
    logger.error(f"コマンドエラー: {error}")

# === Flask起動 ===
def run_flask():
    app.run(host="0.0.0.0", port=PORT, debug=False)

# === メイン実行 ===
if __name__ == "__main__":
    if not TOKEN:
        logger.error("DISCORD_TOKENが設定されていません")
        exit(1)
    
    # Flask を別スレッドで起動
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Discord Bot起動
    try:
        client.run(TOKEN)
    except Exception as e:
        logger.error(f"Bot起動エラー: {e}")
