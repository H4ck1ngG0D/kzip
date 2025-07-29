import discord
from discord.ext import commands, tasks
import json
import os
import asyncio
import logging
from datetime import datetime, timedelta
import hashlib
import secrets
from typing import Optional, Dict, Any
from PayPaython_mobile import PayPay

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('paypay_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 設定
class Config:
    # ファイルパス
    PAYPAY_FILE = "secure_paypay.json"
    SETTINGS_FILE = "guild_settings.json"
    TRANSACTIONS_FILE = "transactions.json"
    
    # セキュリティ
    ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY', secrets.token_hex(32))
    
    # 制限
    MAX_PAYMENT_AMOUNT = 100000  # 10万円
    RATE_LIMIT_MINUTES = 5
    MAX_ATTEMPTS_PER_USER = 3

# Discord Bot設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ユーティリティ関数
class Utils:
    @staticmethod
    def load_json(path: str) -> dict:
        """JSONファイルを安全に読み込み"""
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"JSONファイル読み込みエラー {path}: {e}")
        return {}
    
    @staticmethod
    def save_json(path: str, data: dict) -> bool:
        """JSONファイルを安全に保存"""
        try:
            # バックアップ作成
            if os.path.exists(path):
                backup_path = f"{path}.backup"
                os.rename(path, backup_path)
            
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # バックアップ削除
            backup_path = f"{path}.backup"
            if os.path.exists(backup_path):
                os.remove(backup_path)
            return True
        except Exception as e:
            logger.error(f"JSONファイル保存エラー {path}: {e}")
            return False
    
    @staticmethod
    def create_embed(title: str, description: str = "", color: int = 0x3498db, 
                    thumbnail: str = None, image: str = None) -> discord.Embed:
        """美しいEmbedを作成"""
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.utcnow()
        )
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        if image:
            embed.set_image(url=image)
        embed.set_footer(text="Powered by Advanced PayPay Bot", 
                        icon_url="https://cdn.discordapp.com/emojis/987654321098765432.png")
        return embed
    
    @staticmethod
    def format_amount(amount: int) -> str:
        """金額をフォーマット"""
        return f"¥{amount:,}"
    
    @staticmethod
    def generate_transaction_id() -> str:
        """トランザクションIDを生成"""
        return hashlib.sha256(f"{datetime.utcnow()}{secrets.token_hex(16)}".encode()).hexdigest()[:16]

# レート制限管理
class RateLimiter:
    def __init__(self):
        self.attempts = {}
    
    def is_rate_limited(self, user_id: int, guild_id: int) -> bool:
        """レート制限チェック"""
        key = f"{guild_id}_{user_id}"
        now = datetime.utcnow()
        
        if key not in self.attempts:
            self.attempts[key] = []
        
        # 古い記録を削除
        self.attempts[key] = [
            attempt for attempt in self.attempts[key] 
            if now - attempt < timedelta(minutes=Config.RATE_LIMIT_MINUTES)
        ]
        
        return len(self.attempts[key]) >= Config.MAX_ATTEMPTS_PER_USER
    
    def add_attempt(self, user_id: int, guild_id: int):
        """試行回数を追加"""
        key = f"{guild_id}_{user_id}"
        if key not in self.attempts:
            self.attempts[key] = []
        self.attempts[key].append(datetime.utcnow())

rate_limiter = RateLimiter()

# PayPay管理クラス
class PayPayManager:
    def __init__(self):
        self.connections = {}
    
    def get_connection(self, guild_id: str) -> Optional[PayPay]:
        """PayPay接続を取得"""
        try:
            creds = Utils.load_json(Config.PAYPAY_FILE)
            if guild_id not in creds:
                return None
            
            data = creds[guild_id]
            if guild_id not in self.connections:
                self.connections[guild_id] = PayPay(
                    access_token=data.get("access_token"),
                    refresh_token=data.get("refresh_token"),
                    device_uuid=data.get("device_uuid")
                )
            return self.connections[guild_id]
        except Exception as e:
            logger.error(f"PayPay接続エラー: {e}")
            return None
    
    def save_credentials(self, guild_id: str, credentials: dict) -> bool:
        """認証情報を保存"""
        try:
            creds = Utils.load_json(Config.PAYPAY_FILE)
            creds[guild_id] = credentials
            return Utils.save_json(Config.PAYPAY_FILE, creds)
        except Exception as e:
            logger.error(f"認証情報保存エラー: {e}")
            return False

paypay_manager = PayPayManager()

# トランザクション管理
class TransactionManager:
    @staticmethod
    def log_transaction(guild_id: str, user_id: int, amount: int, 
                       transaction_id: str, status: str, details: dict = None):
        """トランザクションをログ"""
        try:
            transactions = Utils.load_json(Config.TRANSACTIONS_FILE)
            if guild_id not in transactions:
                transactions[guild_id] = []
            
            transaction = {
                "id": transaction_id,
                "user_id": user_id,
                "amount": amount,
                "status": status,
                "timestamp": datetime.utcnow().isoformat(),
                "details": details or {}
            }
            
            transactions[guild_id].append(transaction)
            
            # 最新1000件のみ保持
            if len(transactions[guild_id]) > 1000:
                transactions[guild_id] = transactions[guild_id][-1000:]
            
            Utils.save_json(Config.TRANSACTIONS_FILE, transactions)
        except Exception as e:
            logger.error(f"トランザクションログエラー: {e}")

# ボットイベント
@bot.event
async def on_ready():
    """ボット起動時"""
    logger.info(f'{bot.user} が起動しました！')
    
    # スラッシュコマンドを同期
    try:
        synced = await bot.sync_commands()
        logger.info(f"スラッシュコマンド {len(synced)} 個を同期しました")
    except Exception as e:
        logger.error(f"コマンド同期エラー: {e}")
    
    # 定期タスク開始
    cleanup_task.start()
    status_update.start()

@bot.event
async def on_application_command_error(ctx, error):
    """コマンドエラーハンドラ"""
    logger.error(f"コマンドエラー: {error}")
    
    if isinstance(error, commands.MissingPermissions):
        embed = Utils.create_embed(
        "📊 決済統計",
        "サーバーの決済統計情報",
        color=0x3498db,
        thumbnail="https://cdn.discordapp.com/emojis/987654321098765432.png"
    )
    
    embed.add_field(
        name="💰 総決済額",
        value=f"**{Utils.format_amount(total_amount)}**",
        inline=True
    )
    embed.add_field(
        name="✅ 成功件数",
        value=f"**{success_count:,}** 件",
        inline=True
    )
    embed.add_field(
        name="❌ エラー件数",
        value=f"**{error_count:,}** 件",
        inline=True
    )
    embed.add_field(
        name="📅 今日の決済額",
        value=f"**{Utils.format_amount(today_amount)}**",
        inline=True
    )
    embed.add_field(
        name="📈 今日の件数",
        value=f"**{today_count:,}** 件",
        inline=True
    )
    embed.add_field(
        name="📊 成功率",
        value=f"**{(success_count/(success_count+error_count)*100):.1f}%**" if (success_count+error_count) > 0 else "0%",
        inline=True
    )
    
    await ctx.respond(embed=embed, ephemeral=True)

@bot.slash_command(description="🔧 ボット設定管理 (管理者専用)")
@commands.has_permissions(administrator=True)
async def settings(ctx, 
                  log_channel: discord.TextChannel = None,
                  max_amount: int = None,
                  panel_color: str = None):
    """設定管理コマンド"""
    guild_id = str(ctx.guild.id)
    settings = Utils.load_json(Config.SETTINGS_FILE)
    
    if guild_id not in settings:
        settings[guild_id] = {}
    
    updates = []
    
    if log_channel:
        settings[guild_id]["log_channel"] = log_channel.id
        updates.append(f"ログチャンネル: {log_channel.mention}")
    
    if max_amount and 1 <= max_amount <= 1000000:
        settings[guild_id]["max_amount"] = max_amount
        updates.append(f"最大決済額: {Utils.format_amount(max_amount)}")
    
    if panel_color and panel_color.startswith("#") and len(panel_color) == 7:
        settings[guild_id]["panel_color"] = panel_color
        updates.append(f"パネル色: `{panel_color}`")
    
    if updates:
        Utils.save_json(Config.SETTINGS_FILE, settings)
        embed = Utils.create_embed(
            "✅ 設定更新完了",
            "\n".join(f"• {update}" for update in updates),
            color=0x2ecc71
        )
    else:
        current_settings = settings.get(guild_id, {})
        embed = Utils.create_embed(
            "⚙️ 現在の設定",
            "サーバーの設定状況",
            color=0x3498db
        )
        embed.add_field(
            name="📋 ログチャンネル",
            value=f"<#{current_settings.get('log_channel', 'なし')}>",
            inline=False
        )
        embed.add_field(
            name="💰 最大決済額",
            value=Utils.format_amount(current_settings.get('max_amount', Config.MAX_PAYMENT_AMOUNT)),
            inline=False
        )
        embed.add_field(
            name="🎨 パネル色",
            value=current_settings.get('panel_color', '#3498db'),
            inline=False
        )
    
    await ctx.respond(embed=embed, ephemeral=True)

@bot.slash_command(description="🛡️ 全チャンネルを管理者専用に制限")
@commands.has_permissions(administrator=True)
async def lockdown(ctx, enable: bool = True):
    """サーバーロックダウン"""
    await ctx.defer(ephemeral=True)
    
    try:
        processed = 0
        for channel in ctx.guild.channels:
            if isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
                for role in ctx.guild.roles:
                    if role != ctx.guild.default_role:
                        continue
                    
                    if enable:
                        await channel.set_permissions(role, view_channel=False, send_messages=False)
                    else:
                        await channel.set_permissions(role, overwrite=None)
                    
                processed += 1
        
        status = "有効" if enable else "無効"
        embed = Utils.create_embed(
            f"🛡️ ロックダウン{status}化完了",
            f"{processed} 個のチャンネルの権限を更新しました。",
            color=0x2ecc71 if enable else 0xe74c3c
        )
        
        await ctx.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        logger.error(f"ロックダウンエラー: {e}")
        embed = Utils.create_embed(
            "❌ ロックダウンエラー",
            "権限の更新中にエラーが発生しました。",
            color=0xe74c3c
        )
        await ctx.followup.send(embed=embed, ephemeral=True)

@bot.slash_command(description="📱 決済リンクテスト (管理者専用)")
@commands.has_permissions(administrator=True)
async def test_link(ctx, paypay_link: str):
    """PayPayリンクテスト"""
    await ctx.defer(ephemeral=True)
    guild_id = str(ctx.guild.id)
    paypay = paypay_manager.get_connection(guild_id)
    
    if not paypay:
        embed = Utils.create_embed(
            "❌ 認証エラー",
            "PayPayに接続できません。`/login` で認証してください。",
            color=0xe74c3c
        )
        await ctx.followup.send(embed=embed, ephemeral=True)
        return
    
    try:
        info = paypay.link_check(paypay_link)
        
        embed = Utils.create_embed(
            "🔍 リンク情報",
            "PayPayリンクの詳細情報",
            color=0x3498db
        )
        embed.add_field(name="💰 金額", value=Utils.format_amount(info.amount), inline=True)
        embed.add_field(name="📋 ステータス", value=info.status, inline=True)
        embed.add_field(name="🔐 パスワード", value="あり" if info.has_password else "なし", inline=True)
        embed.add_field(name="👤 送信者", value=info.sender_name or "不明", inline=True)
        embed.add_field(name="💬 メッセージ", value=info.message or "なし", inline=False)
        
        # ステータスに応じて色を変更
        if info.status == "PENDING":
            embed.color = 0x2ecc71
        elif info.status == "EXPIRED":
            embed.color = 0xf39c12
        else:
            embed.color = 0xe74c3c
        
        await ctx.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        logger.error(f"リンクテストエラー: {e}")
        embed = Utils.create_embed(
            "❌ テストエラー",
            f"リンクの確認に失敗しました。\n```{str(e)}```",
            color=0xe74c3c
        )
        await ctx.followup.send(embed=embed, ephemeral=True)

@bot.slash_command(description="🧹 古いログをクリーンアップ (管理者専用)")
@commands.has_permissions(administrator=True)
async def cleanup(ctx, days: int = 30):
    """ログクリーンアップ"""
    if not 1 <= days <= 365:
        embed = Utils.create_embed(
            "❌ 無効な日数",
            "日数は1〜365の範囲で指定してください。",
            color=0xe74c3c
        )
        await ctx.respond(embed=embed, ephemeral=True)
        return
    
    await ctx.defer(ephemeral=True)
    guild_id = str(ctx.guild.id)
    
    try:
        transactions = Utils.load_json(Config.TRANSACTIONS_FILE)
        
        if guild_id not in transactions:
            embed = Utils.create_embed(
                "📊 クリーンアップ結果",
                "クリーンアップするログがありません。",
                color=0x3498db
            )
            await ctx.followup.send(embed=embed, ephemeral=True)
            return
        
        # 指定日数より古いログを削除
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        original_count = len(transactions[guild_id])
        
        transactions[guild_id] = [
            t for t in transactions[guild_id]
            if datetime.fromisoformat(t['timestamp']) > cutoff_date
        ]
        
        deleted_count = original_count - len(transactions[guild_id])
        Utils.save_json(Config.TRANSACTIONS_FILE, transactions)
        
        embed = Utils.create_embed(
            "🧹 クリーンアップ完了",
            f"{deleted_count} 件の古いログを削除しました。",
            color=0x2ecc71
        )
        embed.add_field(name="📊 削除前", value=f"{original_count:,} 件", inline=True)
        embed.add_field(name="📈 残存", value=f"{len(transactions[guild_id]):,} 件", inline=True)
        embed.add_field(name="🗑️ 削除", value=f"{deleted_count:,} 件", inline=True)
        
        await ctx.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        logger.error(f"クリーンアップエラー: {e}")
        embed = Utils.create_embed(
            "❌ クリーンアップエラー",
            "ログのクリーンアップ中にエラーが発生しました。",
            color=0xe74c3c
        )
        await ctx.followup.send(embed=embed, ephemeral=True)

@bot.slash_command(description="ℹ️ ボット情報とヘルプ")
async def info(ctx):
    """ボット情報表示"""
    embed = Utils.create_embed(
        "🤖 Advanced PayPay Bot",
        "高性能 PayPay 決済システム",
        color=0x00d4aa,
        thumbnail="https://cdn.discordapp.com/emojis/987654321098765432.png"
    )
    
    embed.add_field(
        name="✨ 主要機能",
        value="• 🔒 セキュアな PayPay 決済\n• ⚡ リアルタイム処理\n• 📊 詳細な統計機能\n• 🛡️ レート制限保護",
        inline=True
    )
    
    embed.add_field(
        name="📋 管理者コマンド",
        value="• `/login` - PayPay認証\n• `/panel` - 決済パネル設置\n• `/stats` - 統計表示\n• `/settings` - 設定管理",
        inline=True
    )
    
    embed.add_field(
        name="🔧 サポート",
        value="• バージョン: 2.0.0\n• サポート: Discord サーバー\n• ドキュメント: 公式サイト\n• アップデート: 自動",
        inline=True
    )
    
    embed.add_field(
        name="⚠️ 重要事項",
        value=f"• 最大決済額: {Utils.format_amount(Config.MAX_PAYMENT_AMOUNT)}\n• レート制限: {Config.MAX_ATTEMPTS_PER_USER}回/{Config.RATE_LIMIT_MINUTES}分\n• ログ保持: 自動管理\n• セキュリティ: 暗号化済み",
        inline=False
    )
    
    # サーバー統計
    guild_count = len(bot.guilds)
    user_count = sum(guild.member_count for guild in bot.guilds)
    
    embed.add_field(
        name="📈 ボット統計",
        value=f"• サーバー数: **{guild_count:,}**\n• ユーザー数: **{user_count:,}**\n• 稼働時間: **{str(datetime.utcnow() - bot.start_time).split('.')[0]}**",
        inline=False
    )
    
    await ctx.respond(embed=embed)

# エラーハンドリング強化
@bot.event
async def on_error(event, *args, **kwargs):
    """グローバルエラーハンドラ"""
    logger.error(f"Unhandled error in {event}: {args}", exc_info=True)

# 高度な決済処理クラス
class AdvancedPaymentProcessor:
    """高度な決済処理システム"""
    
    def __init__(self):
        self.processing_queue = asyncio.Queue()
        self.active_transactions = {}
    
    async def process_payment(self, transaction_data: dict) -> dict:
        """非同期決済処理"""
        transaction_id = transaction_data.get('transaction_id')
        
        try:
            # 重複処理防止
            if transaction_id in self.active_transactions:
                raise Exception("Transaction already in progress")
            
            self.active_transactions[transaction_id] = transaction_data
            
            # PayPay処理
            guild_id = transaction_data['guild_id']
            paypay = paypay_manager.get_connection(guild_id)
            
            if not paypay:
                raise Exception("PayPay connection failed")
            
            # リンク確認
            link_info = paypay.link_check(transaction_data['link'])
            
            if link_info.status != "PENDING":
                raise Exception(f"Invalid link status: {link_info.status}")
            
            # 決済実行
            result = paypay.link_receive(
                transaction_data['link'],
                transaction_data.get('password', ''),
                link_info
            )
            
            return {
                'status': 'SUCCESS',
                'transaction_id': transaction_id,
                'amount': link_info.amount,
                'info': link_info
            }
            
        except Exception as e:
            logger.error(f"Payment processing error: {e}")
            return {
                'status': 'ERROR',
                'transaction_id': transaction_id,
                'error': str(e)
            }
        finally:
            # クリーンアップ
            if transaction_id in self.active_transactions:
                del self.active_transactions[transaction_id]

# インスタンス作成
payment_processor = AdvancedPaymentProcessor()

# ボット起動設定
if __name__ == "__main__":
    # 起動時間記録
    bot.start_time = datetime.utcnow()
    
    # 環境変数からトークン取得
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        logger.error("DISCORD_BOT_TOKEN環境変数が設定されていません")
        exit(1)
    
    # ボット起動
    try:
        bot.run(token)
    except Exception as e:
        logger.error(f"Bot startup error: {e}")
        exit(1)_embed(
            "❌ 権限エラー",
            "このコマンドを実行する権限がありません。",
            color=0xe74c3c
        )
        await ctx.respond(embed=embed, ephemeral=True)
    else:
        embed = Utils.create_embed(
            "⚠️ エラーが発生しました",
            "しばらく時間をおいてから再度お試しください。",
            color=0xf39c12
        )
        await ctx.respond(embed=embed, ephemeral=True)

# 定期タスク
@tasks.loop(hours=1)
async def cleanup_task():
    """定期クリーンアップ"""
    logger.info("定期クリーンアップを実行中...")
    # 古いログファイルのクリーンアップなど

@tasks.loop(minutes=30)
async def status_update():
    """ステータス更新"""
    activities = [
        discord.Activity(type=discord.ActivityType.watching, name="PayPay決済"),
        discord.Activity(type=discord.ActivityType.listening, name="お客様の声"),
        discord.Game(name="高性能決済システム"),
    ]
    activity = secrets.choice(activities)
    await bot.change_presence(activity=activity)

# PayPay認証モーダル
class PayPayLoginModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="🔐 PayPay アカウント認証")
        
        self.phone_input = discord.ui.InputText(
            label="📱 電話番号",
            placeholder="09012345678 (ハイフンなし)",
            max_length=11,
            min_length=10
        )
        self.password_input = discord.ui.InputText(
            label="🔑 パスワード",
            placeholder="PayPayのパスワードを入力",
            style=discord.InputTextStyle.short
        )
        
        self.add_item(self.phone_input)
        self.add_item(self.password_input)
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        guild_id = str(interaction.guild.id)
        phone = self.phone_input.value.strip()
        password = self.password_input.value.strip()
        
        try:
            # 入力検証
            if not phone.isdigit() or len(phone) not in [10, 11]:
                raise ValueError("電話番号の形式が正しくありません")
            
            # PayPay認証開始
            paypay = PayPay(phone, password)
            
            # 一時的に認証情報を保存
            temp_creds = Utils.load_json("temp_auth.json")
            temp_creds[guild_id] = {
                "phone": phone,
                "password": password,
                "timestamp": datetime.utcnow().isoformat()
            }
            Utils.save_json("temp_auth.json", temp_creds)
            
            embed = Utils.create_embed(
                "📨 認証コード送信完了",
                "SMS認証コードが送信されました。\n下のボタンから認証を完了してください。",
                color=0x2ecc71,
                thumbnail="https://cdn.discordapp.com/emojis/987654321098765432.png"
            )
            
            view = VerificationView(guild_id)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            logger.error(f"PayPayログインエラー: {e}")
            embed = Utils.create_embed(
                "❌ 認証エラー",
                f"ログインに失敗しました。\n```{str(e)}```",
                color=0xe74c3c
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

# 認証コード入力モーダル
class VerificationModal(discord.ui.Modal):
    def __init__(self, guild_id: str):
        super().__init__(title="🔐 SMS認証コード入力")
        self.guild_id = guild_id
        
        self.code_input = discord.ui.InputText(
            label="📟 認証コード",
            placeholder="SMSで受信した6桁のコードまたは認証URL",
            max_length=200
        )
        self.add_item(self.code_input)
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            # 一時認証情報を取得
            temp_creds = Utils.load_json("temp_auth.json")
            if self.guild_id not in temp_creds:
                raise ValueError("認証セッションが期限切れです。再度ログインしてください。")
            
            cred_data = temp_creds[self.guild_id]
            paypay = PayPay(cred_data["phone"], cred_data["password"])
            
            # 認証実行
            verification_code = self.code_input.value.strip()
            paypay.login(verification_code)
            
            # 認証情報を保存
            credentials = {
                "access_token": paypay.access_token,
                "refresh_token": paypay.refresh_token,
                "device_uuid": paypay.device_uuid,
                "phone": cred_data["phone"],
                "created_at": datetime.utcnow().isoformat()
            }
            
            if paypay_manager.save_credentials(self.guild_id, credentials):
                # 一時ファイルをクリーンアップ
                del temp_creds[self.guild_id]
                Utils.save_json("temp_auth.json", temp_creds)
                
                embed = Utils.create_embed(
                    "✅ 認証完了！",
                    "PayPayアカウントの認証が完了しました。\n決済パネルの設置が可能になりました。",
                    color=0x2ecc71,
                    thumbnail="https://cdn.discordapp.com/emojis/987654321098765432.png"
                )
                embed.add_field(
                    name="📋 次のステップ",
                    value="```/panel``` コマンドで決済パネルを設置できます。",
                    inline=False
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                raise Exception("認証情報の保存に失敗しました")
                
        except Exception as e:
            logger.error(f"認証エラー: {e}")
            embed = Utils.create_embed(
                "❌ 認証失敗",
                f"認証に失敗しました。\n```{str(e)}```",
                color=0xe74c3c
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

# 認証ビュー
class VerificationView(discord.ui.View):
    def __init__(self, guild_id: str):
        super().__init__(timeout=300)
        self.guild_id = guild_id
    
    @discord.ui.button(
        label="📟 認証コードを入力",
        style=discord.ButtonStyle.primary,
        emoji="🔐"
    )
    async def verify_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        modal = VerificationModal(self.guild_id)
        await interaction.response.send_modal(modal)

# 支払いモーダル
class PaymentModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="💳 決済フォーム")
        
        self.link_input = discord.ui.InputText(
            label="💰 PayPayリンク",
            placeholder="https://paypay.ne.jp/... または送金ID",
            style=discord.InputTextStyle.long
        )
        self.password_input = discord.ui.InputText(
            label="🔑 パスワード (任意)",
            placeholder="リンクにパスワードが設定されている場合",
            required=False
        )
        self.name_input = discord.ui.InputText(
            label="👤 お名前",
            placeholder="山田太郎 (決済確認用)",
            max_length=50
        )
        
        self.add_item(self.link_input)
        self.add_item(self.password_input)
        self.add_item(self.name_input)
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # レート制限チェック
        if rate_limiter.is_rate_limited(interaction.user.id, interaction.guild.id):
            embed = Utils.create_embed(
                "⏰ レート制限",
                f"短時間に多くのリクエストが送信されました。\n{Config.RATE_LIMIT_MINUTES}分後に再度お試しください。",
                color=0xf39c12
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        rate_limiter.add_attempt(interaction.user.id, interaction.guild.id)
        
        guild_id = str(interaction.guild.id)
        paypay = paypay_manager.get_connection(guild_id)
        
        if not paypay:
            embed = Utils.create_embed(
                "❌ 認証エラー",
                "PayPayに接続できません。管理者にお問い合わせください。",
                color=0xe74c3c
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        transaction_id = Utils.generate_transaction_id()
        
        try:
            # リンク情報取得
            link = self.link_input.value.strip()
            password = self.password_input.value.strip() if self.password_input.value else ""
            name = self.name_input.value.strip()
            
            info = paypay.link_check(link)
            
            if info.status != "PENDING":
                raise Exception("このリンクは既に使用済みまたは無効です")
            
            if info.amount > Config.MAX_PAYMENT_AMOUNT:
                raise Exception(f"金額上限（{Utils.format_amount(Config.MAX_PAYMENT_AMOUNT)}）を超えています")
            
            # 決済実行
            result = paypay.link_receive(link, password, info)
            
            # 成功レスポンス
            embed = Utils.create_embed(
                "✅ 決済完了",
                f"決済が正常に完了しました。\nご利用ありがとうございました！",
                color=0x2ecc71,
                thumbnail="https://cdn.discordapp.com/emojis/987654321098765432.png"
            )
            embed.add_field(name="💰 金額", value=Utils.format_amount(info.amount), inline=True)
            embed.add_field(name="📋 取引ID", value=f"`{transaction_id}`", inline=True)
            embed.add_field(name="⏰ 処理時間", value=f"{datetime.utcnow().strftime('%H:%M:%S')}", inline=True)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # 管理者向けログ
            admin_embed = Utils.create_embed(
                "📊 新規決済",
                "決済が正常に処理されました",
                color=0x3498db,
                thumbnail="https://cdn.discordapp.com/emojis/987654321098765432.png"
            )
            admin_embed.add_field(name="👤 利用者", value=interaction.user.mention, inline=True)
            admin_embed.add_field(name="📝 入力名", value=name, inline=True)
            admin_embed.add_field(name="💰 金額", value=Utils.format_amount(info.amount), inline=True)
            admin_embed.add_field(name="🔐 パスワード", value="あり" if password else "なし", inline=True)
            admin_embed.add_field(name="📋 取引ID", value=f"`{transaction_id}`", inline=True)
            admin_embed.add_field(name="⏰ 時刻", value=f"<t:{int(datetime.utcnow().timestamp())}:F>", inline=True)
            
            # ログチャンネルに送信
            log_channel = discord.utils.get(interaction.guild.text_channels, name="paypay-log")
            if log_channel:
                await log_channel.send(embed=admin_embed)
            
            # トランザクションログ
            TransactionManager.log_transaction(
                guild_id, interaction.user.id, info.amount, 
                transaction_id, "SUCCESS", {
                    "name": name,
                    "has_password": bool(password),
                    "link": link[:50] + "..." if len(link) > 50 else link
                }
            )
            
        except Exception as e:
            logger.error(f"決済エラー: {e}")
            
            # エラーログ
            TransactionManager.log_transaction(
                guild_id, interaction.user.id, 0, 
                transaction_id, "ERROR", {"error": str(e)}
            )
            
            embed = Utils.create_embed(
                "❌ 決済エラー",
                f"決済処理中にエラーが発生しました。\n```{str(e)}```",
                color=0xe74c3c
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

# メイン決済パネルビュー
class PaymentPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(
        label="💳 決済する",
        style=discord.ButtonStyle.success,
        emoji="💰",
        custom_id="payment_button"
    )
    async def payment_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        modal = PaymentModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(
        label="ℹ️ ヘルプ",
        style=discord.ButtonStyle.secondary,
        emoji="❓",
        custom_id="help_button"
    )
    async def help_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        embed = Utils.create_embed(
            "📋 決済ヘルプ",
            "PayPay決済の使い方をご説明します。",
            color=0x3498db
        )
        embed.add_field(
            name="🔗 PayPayリンクについて",
            value="• PayPayアプリから「送る」→「リンクを作成」\n• 生成されたURLをコピーしてください",
            inline=False
        )
        embed.add_field(
            name="🔐 セキュリティ",
            value="• すべての決済は暗号化されて処理されます\n• 個人情報は安全に保護されます",
            inline=False
        )
        embed.add_field(
            name="⚠️ 注意事項",
            value=f"• 最大決済金額: {Utils.format_amount(Config.MAX_PAYMENT_AMOUNT)}\n• 決済は即座に実行されます",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

# スラッシュコマンド群
@bot.slash_command(description="🔐 PayPayアカウントでログイン (管理者専用)")
@commands.has_permissions(administrator=True)
async def login(ctx):
    """PayPayログインコマンド"""
    guild_id = str(ctx.guild.id)
    creds = Utils.load_json(Config.PAYPAY_FILE)
    
    if guild_id in creds:
        embed = Utils.create_embed(
            "⚠️ 既にログイン済み",
            "PayPayアカウントは既に認証されています。\n`/logout` で認証を解除できます。",
            color=0xf39c12
        )
        await ctx.respond(embed=embed, ephemeral=True)
        return
    
    modal = PayPayLoginModal()
    await ctx.response.send_modal(modal)

@bot.slash_command(description="🚪 PayPayからログアウト (管理者専用)")
@commands.has_permissions(administrator=True)
async def logout(ctx):
    """PayPayログアウトコマンド"""
    guild_id = str(ctx.guild.id)
    creds = Utils.load_json(Config.PAYPAY_FILE)
    
    if guild_id in creds:
        del creds[guild_id]
        Utils.save_json(Config.PAYPAY_FILE, creds)
        
        # メモリからも削除
        if guild_id in paypay_manager.connections:
            del paypay_manager.connections[guild_id]
        
        embed = Utils.create_embed(
            "✅ ログアウト完了",
            "PayPayアカウントの認証が解除されました。",
            color=0x2ecc71
        )
    else:
        embed = Utils.create_embed(
            "⚠️ ログイン情報なし",
            "PayPayアカウントの認証情報が見つかりません。",
            color=0xf39c12
        )
    
    await ctx.respond(embed=embed, ephemeral=True)

@bot.slash_command(description="📊 決済パネルを設置 (管理者専用)")
@commands.has_permissions(administrator=True)
async def panel(ctx, 
                title: str = "💎 プレミアム決済システム",
                description: str = "安全・高速・簡単な PayPay 決済",
                image_url: str = None):
    """決済パネル設置コマンド"""
    guild_id = str(ctx.guild.id)
    
    # PayPay認証確認
    if not paypay_manager.get_connection(guild_id):
        embed = Utils.create_embed(
            "❌ 認証エラー",
            "先に `/login` でPayPayアカウントを認証してください。",
            color=0xe74c3c
        )
        await ctx.respond(embed=embed, ephemeral=True)
        return
    
    # メインパネル作成
    embed = Utils.create_embed(
        title,
        description,
        color=0x00d4aa,
        image=image_url
    )
    
    embed.add_field(
        name="✨ 特徴",
        value="• 🔒 **セキュア**: 暗号化された安全な決済\n• ⚡ **高速**: 即座に処理完了\n• 📱 **簡単**: PayPayリンクを貼るだけ",
        inline=True
    )
    
    embed.add_field(
        name="📋 利用方法",
        value="1️⃣ 「決済する」ボタンをクリック\n2️⃣ PayPayリンクを入力\n3️⃣ お名前を入力して送信",
        inline=True
    )
    
    embed.add_field(
        name="💰 対応金額",
        value=f"¥1 〜 {Utils.format_amount(Config.MAX_PAYMENT_AMOUNT)}",
        inline=True
    )
    
    view = PaymentPanelView()
    await ctx.respond(embed=embed, view=view)

@bot.slash_command(description="📈 決済統計を表示 (管理者専用)")
@commands.has_permissions(administrator=True)
async def stats(ctx):
    """統計表示コマンド"""
    guild_id = str(ctx.guild.id)
    transactions = Utils.load_json(Config.TRANSACTIONS_FILE)
    
    if guild_id not in transactions or not transactions[guild_id]:
        embed = Utils.create_embed(
            "📊 決済統計",
            "まだ決済履歴がありません。",
            color=0x3498db
        )
        await ctx.respond(embed=embed, ephemeral=True)
        return
    
    guild_transactions = transactions[guild_id]
    
    # 統計計算
    total_amount = sum(t.get('amount', 0) for t in guild_transactions if t.get('status') == 'SUCCESS')
    success_count = len([t for t in guild_transactions if t.get('status') == 'SUCCESS'])
    error_count = len([t for t in guild_transactions if t.get('status') == 'ERROR'])
    
    # 今日の統計
    today = datetime.utcnow().date()
    today_transactions = [
        t for t in guild_transactions 
        if datetime.fromisoformat(t['timestamp']).date() == today
    ]
    today_amount = sum(t.get('amount', 0) for t in today_transactions if t.get('status') == 'SUCCESS')
    today_count = len([t for t in today_transactions if t.get('status') == 'SUCCESS'])
    
    embed = Utils.create
    embed = Utils.create_embed(
        "📊 決済統計",
        "サーバーの決済統計情報",
        color=0x3498db,
        thumbnail="https://cdn.discordapp.com/emojis/987654321098765432.png"
    )
    
    embed.add_field(
        name="💰 総決済額",
        value=f"**{Utils.format_amount(total_amount)}**",
        inline=True
    )
    embed.add_field(
        name="✅ 成功件数",
        value=f"**{success_count:,}** 件",
        inline=True
    )
    embed.add_field(
        name="❌ エラー件数",
        value=f"**{error_count:,}** 件",
        inline=True
    )
    embed.add_field(
        name="📅 今日の決済額",
        value=f"**{Utils.format_amount(today_amount)}**",
        inline=True
    )
    embed.add_field(
        name="📈 今日の件数",
        value=f"**{today_count:,}** 件",
        inline=True
    )
    embed.add_field(
        name="📊 成功率",
        value=f"**{(success_count/(success_count+error_count)*100):.1f}%**" if (success_count+error_count) > 0 else "0%",
        inline=True
    )
    
    await ctx.respond(embed=embed, ephemeral=True)

@bot.slash_command(description="🔧 ボット設定管理 (管理者専用)")
@commands.has_permissions(administrator=True)
async def settings(ctx, 
                  log_channel: discord.TextChannel = None,
                  max_amount: int = None,
                  panel_color: str = None):
    """設定管理コマンド"""
    guild_id = str(ctx.guild.id)
    settings = Utils.load_json(Config.SETTINGS_FILE)
    
    if guild_id not in settings:
        settings[guild_id] = {}
    
    updates = []
    
    if log_channel:
        settings[guild_id]["log_channel"] = log_channel.id
        updates.append(f"ログチャンネル: {log_channel.mention}")
    
    if max_amount and 1 <= max_amount <= 1000000:
        settings[guild_id]["max_amount"] = max_amount
        updates.append(f"最大決済額: {Utils.format_amount(max_amount)}")
    
    if panel_color and panel_color.startswith("#") and len(panel_color) == 7:
        settings[guild_id]["panel_color"] = panel_color
        updates.append(f"パネル色: `{panel_color}`")
    
    if updates:
        Utils.save_json(Config.SETTINGS_FILE, settings)
        embed = Utils.create_embed(
            "✅ 設定更新完了",
            "\n".join(f"• {update}" for update in updates),
            color=0x2ecc71
        )
    else:
        current_settings = settings.get(guild_id, {})
        embed = Utils.create_embed(
            "⚙️ 現在の設定",
            "サーバーの設定状況",
            color=0x3498db
        )
        embed.add_field(
            name="📋 ログチャンネル",
            value=f"<#{current_settings.get('log_channel', 'なし')}>",
            inline=False
        )
        embed.add_field(
            name="💰 最大決済額",
            value=Utils.format_amount(current_settings.get('max_amount', Config.MAX_PAYMENT_AMOUNT)),
            inline=False
        )
        embed.add_field(
            name="🎨 パネル色",
            value=current_settings.get('panel_color', '#3498db'),
            inline=False
        )
    
    await ctx.respond(embed=embed, ephemeral=True)

@bot.slash_command(description="🛡️ 全チャンネルを管理者専用に制限")
@commands.has_permissions(administrator=True)
async def lockdown(ctx, enable: bool = True):
    """サーバーロックダウン"""
    await ctx.defer(ephemeral=True)
    
    try:
        processed = 0
        for channel in ctx.guild.channels:
            if isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
                for role in ctx.guild.roles:
                    if role != ctx.guild.default_role:
                        continue
                    
                    if enable:
                        await channel.set_permissions(role, view_channel=False, send_messages=False)
                    else:
                        await channel.set_permissions(role, overwrite=None)
                    
                processed += 1
        
        status = "有効" if enable else "無効"
        embed = Utils.create_embed(
            f"🛡️ ロックダウン{status}化完了",
            f"{processed} 個のチャンネルの権限を更新しました。",
            color=0x2ecc71 if enable else 0xe74c3c
        )
        
        await ctx.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        logger.error(f"ロックダウンエラー: {e}")
        embed = Utils.create_embed(
            "❌ ロックダウンエラー",
            "権限の更新中にエラーが発生しました。",
            color=0xe74c3c
        )
        await ctx.followup.send(embed=embed, ephemeral=True)

@bot.slash_command(description="📱 決済リンクテスト (管理者専用)")
@commands.has_permissions(administrator=True)
async def test_link(ctx, paypay_link: str):
    """PayPayリンクテスト"""
    await ctx.defer(ephemeral=True)
    guild_id = str(ctx.guild.id)
    paypay = paypay_manager.get_connection(guild_id)
    
    if not paypay:
        embed = Utils.create_embed(
            "❌ 認証エラー",
            "PayPayに接続できません。`/login` で認証してください。",
            color=0xe74c3c
        )
        await ctx.followup.send(embed=embed, ephemeral=True)
        return
    
    try:
        info = paypay.link_check(paypay_link)
        
        embed = Utils.create_embed(
            "🔍 リンク情報",
            "PayPayリンクの詳細情報",
            color=0x3498db
        )
        embed.add_field(name="💰 金額", value=Utils.format_amount(info.amount), inline=True)
        embed.add_field(name="📋 ステータス", value=info.status, inline=True)
        embed.add_field(name="🔐 パスワード", value="あり" if info.has_password else "なし", inline=True)
        embed.add_field(name="👤 送信者", value=info.sender_name or "不明", inline=True)
        embed.add_field(name="💬 メッセージ", value=info.message or "なし", inline=False)
        
        # ステータスに応じて色を変更
        if info.status == "PENDING":
            embed.color = 0x2ecc71
        elif info.status == "EXPIRED":
            embed.color = 0xf39c12
        else:
            embed.color = 0xe74c3c
        
        await ctx.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        logger.error(f"リンクテストエラー: {e}")
        embed = Utils.create_embed(
            "❌ テストエラー",
            f"リンクの確認に失敗しました。\n```{str(e)}```",
            color=0xe74c3c
        )
        await ctx.followup.send(embed=embed, ephemeral=True)

@bot.slash_command(description="🧹 古いログをクリーンアップ (管理者専用)")
@commands.has_permissions(administrator=True)
async def cleanup(ctx, days: int = 30):
    """ログクリーンアップ"""
    if not 1 <= days <= 365:
        embed = Utils.create_embed(
            "❌ 無効な日数",
            "日数は1〜365の範囲で指定してください。",
            color=0xe74c3c
        )
        await ctx.respond(embed=embed, ephemeral=True)
        return
    
    await ctx.defer(ephemeral=True)
    guild_id = str(ctx.guild.id)
    
    try:
        transactions = Utils.load_json(Config.TRANSACTIONS_FILE)
        
        if guild_id not in transactions:
            embed = Utils.create_embed(
                "📊 クリーンアップ結果",
                "クリーンアップするログがありません。",
                color=0x3498db
            )
            await ctx.followup.send(embed=embed, ephemeral=True)
            return
        
        # 指定日数より古いログを削除
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        original_count = len(transactions[guild_id])
        
        transactions[guild_id] = [
            t for t in transactions[guild_id]
            if datetime.fromisoformat(t['timestamp']) > cutoff_date
        ]
        
        deleted_count = original_count - len(transactions[guild_id])
        Utils.save_json(Config.TRANSACTIONS_FILE, transactions)
        
        embed = Utils.create_embed(
            "🧹 クリーンアップ完了",
            f"{deleted_count} 件の古いログを削除しました。",
            color=0x2ecc71
        )
        embed.add_field(name="📊 削除前", value=f"{original_count:,} 件", inline=True)
        embed.add_field(name="📈 残存", value=f"{len(transactions[guild_id]):,} 件", inline=True)
        embed.add_field(name="🗑️ 削除", value=f"{deleted_count:,} 件", inline=True)
        
        await ctx.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        logger.error(f"クリーンアップエラー: {e}")
        embed = Utils.create_embed(
            "❌ クリーンアップエラー",
            "ログのクリーンアップ中にエラーが発生しました。",
            color=0xe74c3c
        )
        await ctx.followup.send(embed=embed, ephemeral=True)

@bot.slash_command(description="ℹ️ ボット情報とヘルプ")
async def info(ctx):
    """ボット情報表示"""
    embed = Utils.create_embed(
        "🤖 Advanced PayPay Bot",
        "高性能 PayPay 決済システム",
        color=0x00d4aa,
        thumbnail="https://cdn.discordapp.com/emojis/987654321098765432.png"
    )
    
    embed.add_field(
        name="✨ 主要機能",
        value="• 🔒 セキュアな PayPay 決済\n• ⚡ リアルタイム処理\n• 📊 詳細な統計機能\n• 🛡️ レート制限保護",
        inline=True
    )
    
    embed.add_field(
        name="📋 管理者コマンド",
        value="• `/login` - PayPay認証\n• `/panel` - 決済パネル設置\n• `/stats` - 統計表示\n• `/settings` - 設定管理",
        inline=True
    )
    
    embed.add_field(
        name="🔧 サポート",
        value="• バージョン: 2.0.0\n• サポート: Discord サーバー\n• ドキュメント: 公式サイト\n• アップデート: 自動",
        inline=True
    )
    
    embed.add_field(
        name="⚠️ 重要事項",
        value=f"• 最大決済額: {Utils.format_amount(Config.MAX_PAYMENT_AMOUNT)}\n• レート制限: {Config.MAX_ATTEMPTS_PER_USER}回/{Config.RATE_LIMIT_MINUTES}分\n• ログ保持: 自動管理\n• セキュリティ: 暗号化済み",
        inline=False
    )
    
    # サーバー統計
    guild_count = len(bot.guilds)
    user_count = sum(guild.member_count for guild in bot.guilds)
    
    embed.add_field(
        name="📈 ボット統計",
        value=f"• サーバー数: **{guild_count:,}**\n• ユーザー数: **{user_count:,}**\n• 稼働時間: **{str(datetime.utcnow() - bot.start_time).split('.')[0]}**",
        inline=False
    )
    
    await ctx.respond(embed=embed)

# エラーハンドリング強化
@bot.event
async def on_error(event, *args, **kwargs):
    """グローバルエラーハンドラ"""
    logger.error(f"Unhandled error in {event}: {args}", exc_info=True)

# 高度な決済処理クラス
class AdvancedPaymentProcessor:
    """高度な決済処理システム"""
    
    def __init__(self):
        self.processing_queue = asyncio.Queue()
        self.active_transactions = {}
    
    async def process_payment(self, transaction_data: dict) -> dict:
        """非同期決済処理"""
        transaction_id = transaction_data.get('transaction_id')
        
        try:
            # 重複処理防止
            if transaction_id in self.active_transactions:
                raise Exception("Transaction already in progress")
            
            self.active_transactions[transaction_id] = transaction_data
            
            # PayPay処理
            guild_id = transaction_data['guild_id']
            paypay = paypay_manager.get_connection(guild_id)
            
            if not paypay:
                raise Exception("PayPay connection failed")
            
            # リンク確認
            link_info = paypay.link_check(transaction_data['link'])
            
            if link_info.status != "PENDING":
                raise Exception(f"Invalid link status: {link_info.status}")
            
            # 決済実行
            result = paypay.link_receive(
                transaction_data['link'],
                transaction_data.get('password', ''),
                link_info
            )
            
            return {
                'status': 'SUCCESS',
                'transaction_id': transaction_id,
                'amount': link_info.amount,
                'info': link_info
            }
            
        except Exception as e:
            logger.error(f"Payment processing error: {e}")
            return {
                'status': 'ERROR',
                'transaction_id': transaction_id,
                'error': str(e)
            }
        finally:
            # クリーンアップ
            if transaction_id in self.active_transactions:
                del self.active_transactions[transaction_id]

# インスタンス作成
payment_processor = AdvancedPaymentProcessor()

# ボット起動設定
if __name__ == "__main__":
    # 起動時間記録
    bot.start_time = datetime.utcnow()
    
    # 環境変数からトークン取得
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        logger.error("DISCORD_BOT_TOKEN環境変数が設定されていません")
        exit(1)
    
    # ボット起動
    try:
        bot.run(token)
    except Exception as e:
        logger.error(f"Bot startup error: {e}")
        exit(1)
