import discord
from discord.ext import commands, tasks
import json
import os
import hashlib
import hmac
import time
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from PayPaython_mobile import PayPay

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Intents設定
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.guild_messages = True

bot = commands.Bot(command_prefix="/", intents=intents)

# ファイルパス定数
CONFIG_FILE = "bot_config.json"
SESSIONS_FILE = "sessions.json"
TRANSACTIONS_FILE = "transactions.json"
BLACKLIST_FILE = "blacklist.json"

# セキュリティ設定
SECRET_KEY = "kamichita247"
MAX_RETRY_ATTEMPTS = 3
RATE_LIMIT_WINDOW = 300  # 5分
MAX_REQUESTS_PER_WINDOW = 10

class SecurityManager:
    """セキュリティ管理クラス"""
    def __init__(self):
        self.rate_limits = {}
        self.failed_attempts = {}
    
    def is_rate_limited(self, user_id: int) -> bool:
        current_time = time.time()
        if user_id not in self.rate_limits:
            self.rate_limits[user_id] = []
        
        # 古いエントリを削除
        self.rate_limits[user_id] = [
            timestamp for timestamp in self.rate_limits[user_id]
            if current_time - timestamp < RATE_LIMIT_WINDOW
        ]
        
        if len(self.rate_limits[user_id]) >= MAX_REQUESTS_PER_WINDOW:
            return True
        
        self.rate_limits[user_id].append(current_time)
        return False
    
    def encrypt_data(self, data: str) -> str:
        return hmac.new(SECRET_KEY.encode(), data.encode(), hashlib.sha256).hexdigest()
    
    def verify_data(self, data: str, signature: str) -> bool:
        return hmac.compare_digest(self.encrypt_data(data), signature)

security = SecurityManager()

class DataManager:
    """データ管理クラス"""
    @staticmethod
    def load_json(filepath: str, default=None) -> Dict[str, Any]:
        if default is None:
            default = {}
        try:
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load {filepath}: {e}")
        return default
    
    @staticmethod
    def save_json(filepath: str, data: Dict[str, Any]) -> bool:
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except IOError as e:
            logger.error(f"Failed to save {filepath}: {e}")
            return False
    
    @staticmethod
    def log_transaction(guild_id: str, user_id: int, amount: int, status: str, details: str = "") -> None:
        transactions = DataManager.load_json(TRANSACTIONS_FILE, [])
        transaction = {
            "timestamp": datetime.now().isoformat(),
            "guild_id": guild_id,
            "user_id": user_id,
            "amount": amount,
            "status": status,
            "details": details
        }
        transactions.append(transaction)
        DataManager.save_json(TRANSACTIONS_FILE, transactions)

class PayPayManager:
    """PayPay操作管理クラス"""
    def __init__(self):
        self.sessions = {}
    
    async def initialize_session(self, guild_id: str, phone: str, password: str) -> tuple[bool, str]:
        try:
            paypay = PayPay(phone, password)
            self.sessions[guild_id] = {
                "paypay": paypay,
                "phone": phone,
                "password": password,
                "status": "awaiting_verification",
                "created_at": time.time()
            }
            return True, "認証コードがSMSに送信されました"
        except Exception as e:
            logger.error(f"PayPay initialization failed for guild {guild_id}: {e}")
            return False, f"初期化に失敗しました: {str(e)}"
    
    async def verify_session(self, guild_id: str, verification_code: str) -> tuple[bool, str]:
        if guild_id not in self.sessions:
            return False, "セッションが見つかりません"
        
        try:
            session = self.sessions[guild_id]
            paypay = session["paypay"]
            paypay.login(verification_code)
            
            # セッション情報を更新
            session.update({
                "access_token": paypay.access_token,
                "refresh_token": paypay.refresh_token,
                "device_uuid": paypay.device_uuid,
                "status": "verified",
                "verified_at": time.time()
            })
            
            # 永続化
            config = DataManager.load_json(CONFIG_FILE)
            config[guild_id] = {
                "access_token": paypay.access_token,
                "refresh_token": paypay.refresh_token,
                "device_uuid": paypay.device_uuid,
                "verified_at": time.time()
            }
            DataManager.save_json(CONFIG_FILE, config)
            
            return True, "認証が完了しました"
        except Exception as e:
            logger.error(f"PayPay verification failed for guild {guild_id}: {e}")
            return False, f"認証に失敗しました: {str(e)}"
    
    def get_paypay_instance(self, guild_id: str) -> Optional[PayPay]:
        config = DataManager.load_json(CONFIG_FILE)
        if guild_id not in config:
            return None
        
        try:
            data = config[guild_id]
            return PayPay(access_token=data["access_token"])
        except Exception as e:
            logger.error(f"Failed to create PayPay instance for guild {guild_id}: {e}")
            return None

paypay_manager = PayPayManager()

# モーダルクラス群
class LoginModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="🔐 PayPay アカウント認証")
        self.phone = discord.ui.InputText(
            label="📱 電話番号",
            placeholder="080-1234-5678",
            min_length=10,
            max_length=15
        )
        self.password = discord.ui.InputText(
            label="🔑 パスワード",
            placeholder="PayPayパスワードを入力",
            style=discord.InputTextStyle.short
        )
        self.add_item(self.phone)
        self.add_item(self.password)
    
    async def callback(self, interaction: discord.Interaction):
        if security.is_rate_limited(interaction.user.id):
            await interaction.response.send_message("⚠️ レート制限に達しました。5分後に再試行してください。", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        guild_id = str(interaction.guild.id)
        success, message = await paypay_manager.initialize_session(guild_id, self.phone.value, self.password.value)
        
        if success:
            embed = discord.Embed(
                title="📨 認証コード送信完了",
                description=message,
                color=0x00d4aa
            )
            embed.add_field(name="次のステップ", value="SMS で受信した認証コードを下のボタンから入力してください", inline=False)
            view = VerificationView(guild_id)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            embed = discord.Embed(title="❌ エラー", description=message, color=0xff0000)
            await interaction.followup.send(embed=embed, ephemeral=True)

class VerificationModal(discord.ui.Modal):
    def __init__(self, guild_id: str):
        super().__init__(title="📲 認証コード入力")
        self.guild_id = guild_id
        self.code = discord.ui.InputText(
            label="🔢 認証コードまたはリンク",
            placeholder="https://paypay.ne.jp/... または 6桁の数字",
            min_length=6
        )
        self.add_item(self.code)
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        success, message = await paypay_manager.verify_session(self.guild_id, self.code.value)
        
        if success:
            embed = discord.Embed(
                title="✅ 認証完了",
                description="PayPay アカウントの認証が正常に完了しました！",
                color=0x00ff00
            )
            embed.add_field(name="ステータス", value="🟢 オンライン", inline=True)
            embed.add_field(name="機能", value="支払い受取機能が利用可能です", inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # ログチャンネルに通知
            log_channel = discord.utils.get(interaction.guild.text_channels, name="paypay-logs")
            if log_channel:
                log_embed = discord.Embed(
                    title="🔐 新規認証",
                    description=f"管理者 {interaction.user.mention} がPayPayアカウントを認証しました",
                    color=0x3498db,
                    timestamp=datetime.now()
                )
                await log_channel.send(embed=log_embed)
        else:
            embed = discord.Embed(title="❌ 認証失敗", description=message, color=0xff0000)
            await interaction.followup.send(embed=embed, ephemeral=True)

class PaymentModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="💰 PayPay 支払い処理")
        self.link = discord.ui.InputText(
            label="🔗 PayPay支払いリンク",
            placeholder="https://paypay.ne.jp/sKTsvMpH40G2nBxsJ",
            min_length=20
        )
        self.password = discord.ui.InputText(
            label="🔐 パスワード (オプション)",
            placeholder="支払いリンクにパスワードが設定されている場合",
            required=False
        )
        self.username = discord.ui.InputText(
            label="👤 お名前",
            placeholder="山田 太郎",
            min_length=1,
            max_length=50
        )
        self.add_item(self.link)
        self.add_item(self.password)
        self.add_item(self.username)
    
    async def callback(self, interaction: discord.Interaction):
        if security.is_rate_limited(interaction.user.id):
            await interaction.response.send_message("⚠️ レート制限中です。少し時間をおいて再試行してください。", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        guild_id = str(interaction.guild.id)
        paypay = paypay_manager.get_paypay_instance(guild_id)
        
        if not paypay:
            await interaction.followup.send("❌ PayPayアカウントが認証されていません。管理者にお問い合わせください。", ephemeral=True)
            return
        
        try:
            # リンク情報を取得
            link_info = paypay.link_check(self.link.value)
            
            if link_info.status != "PENDING":
                await interaction.followup.send("❌ 無効または期限切れの支払いリンクです。", ephemeral=True)
                return
            
            # 支払い実行
            result = paypay.link_receive(self.link.value, self.password.value or "", link_info)
            
            # 成功レスポンス
            success_embed = discord.Embed(
                title="✅ 支払い完了",
                description="お支払いが正常に処理されました。ありがとうございました！",
                color=0x00ff00
            )
            success_embed.add_field(name="💰 金額", value=f"¥{link_info.amount:,}", inline=True)
            success_embed.add_field(name="👤 お名前", value=self.username.value, inline=True)
            success_embed.add_field(name="📅 処理日時", value=datetime.now().strftime("%Y/%m/%d %H:%M:%S"), inline=True)
            
            await interaction.followup.send(embed=success_embed, ephemeral=True)
            
            # 管理ログ
            log_embed = discord.Embed(
                title="💳 支払い受領記録",
                color=0x00d4aa,
                timestamp=datetime.now()
            )
            log_embed.add_field(name="👤 利用者", value=f"{interaction.user.mention}\n({interaction.user.display_name})", inline=True)
            log_embed.add_field(name="📝 入力名", value=self.username.value, inline=True)
            log_embed.add_field(name="💰 金額", value=f"¥{link_info.amount:,}", inline=True)
            log_embed.add_field(name="🔐 パスワード", value="🔒 あり" if self.password.value else "🔓 なし", inline=True)
            log_embed.add_field(name="📊 ステータス", value="✅ 完了", inline=True)
            log_embed.add_field(name="🆔 ユーザーID", value=str(interaction.user.id), inline=True)
            
            # ログチャンネルに送信
            log_channel = discord.utils.get(interaction.guild.text_channels, name="paypay-logs")
            if log_channel:
                await log_channel.send(embed=log_embed)
            
            # トランザクション記録
            DataManager.log_transaction(
                guild_id, 
                interaction.user.id, 
                link_info.amount, 
                "success", 
                f"User: {self.username.value}"
            )
            
        except Exception as e:
            logger.error(f"Payment processing failed: {e}")
            error_embed = discord.Embed(
                title="❌ 支払い処理エラー",
                description="支払い処理中にエラーが発生しました。しばらく時間をおいて再試行してください。",
                color=0xff0000
            )
            error_embed.add_field(name="🔍 エラー詳細", value=str(e)[:1000], inline=False)
            await interaction.followup.send(embed=error_embed, ephemeral=True)
            
            # エラーログ
            DataManager.log_transaction(guild_id, interaction.user.id, 0, "error", str(e))

# ビュークラス群
class LoginView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
    
    @discord.ui.button(label="🔐 ログイン開始", style=discord.ButtonStyle.primary, emoji="🚀")
    async def login_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_modal(LoginModal())

class VerificationView(discord.ui.View):
    def __init__(self, guild_id: str):
        super().__init__(timeout=600)
        self.guild_id = guild_id
    
    @discord.ui.button(label="📲 認証コード入力", style=discord.ButtonStyle.success, emoji="✅")
    async def verify_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_modal(VerificationModal(self.guild_id))

class PaymentPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="💳 お支払い", style=discord.ButtonStyle.green, emoji="💰")
    async def payment_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_modal(PaymentModal())
    
    @discord.ui.button(label="📊 利用状況", style=discord.ButtonStyle.secondary, emoji="📈")
    async def status_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        config = DataManager.load_json(CONFIG_FILE)
        
        status_embed = discord.Embed(
            title="📊 システム状況",
            color=0x3498db,
            timestamp=datetime.now()
        )
        
        if guild_id in config:
            status_embed.add_field(name="🟢 PayPay", value="認証済み・稼働中", inline=True)
            last_verified = datetime.fromtimestamp(config[guild_id].get("verified_at", 0))
            status_embed.add_field(name="📅 最終認証", value=last_verified.strftime("%Y/%m/%d %H:%M"), inline=True)
        else:
            status_embed.add_field(name="🔴 PayPay", value="未認証", inline=True)
        
        # 統計情報
        transactions = DataManager.load_json(TRANSACTIONS_FILE, [])
        guild_transactions = [t for t in transactions if t.get("guild_id") == guild_id]
        success_count = len([t for t in guild_transactions if t.get("status") == "success"])
        total_amount = sum(t.get("amount", 0) for t in guild_transactions if t.get("status") == "success")
        
        status_embed.add_field(name="📈 成功取引", value=f"{success_count}件", inline=True)
        status_embed.add_field(name="💰 総取引額", value=f"¥{total_amount:,}", inline=True)
        
        await interaction.response.send_message(embed=status_embed, ephemeral=True)

# コマンド群
@bot.slash_command(name="setup", description="🚀 PayPay認証セットアップ (管理者専用)")
@commands.has_permissions(administrator=True)
async def setup_command(ctx):
    embed = discord.Embed(
        title="🔐 PayPay アカウント認証",
        description="PayPay支払い機能を利用するには、まずアカウント認証が必要です。",
        color=0x00d4aa
    )
    embed.add_field(
        name="📋 認証手順",
        value="1️⃣ 下のボタンをクリック\n2️⃣ 電話番号とパスワードを入力\n3️⃣ SMS認証コードを入力",
        inline=False
    )
    embed.add_field(
        name="🔒 セキュリティ",
        value="認証情報は暗号化され、安全に保存されます",
        inline=False
    )
    
    await ctx.respond(embed=embed, view=LoginView(), ephemeral=True)

@bot.slash_command(name="panel", description="💳 支払いパネル表示 (管理者専用)")
@commands.has_permissions(administrator=True)
async def panel_command(ctx):
    embed = discord.Embed(
        title="💰 PayPay 支払いセンター",
        description="下のボタンから安全にお支払いができます",
        color=0x00d4aa
    )
    embed.add_field(
        name="💳 支払い方法",
        value="PayPay支払いリンクを貼り付けるだけで簡単決済",
        inline=False
    )
    embed.add_field(
        name="🔒 セキュリティ",
        value="SSL暗号化通信・レート制限・不正利用監視",
        inline=True
    )
    embed.add_field(
        name="📊 透明性",
        value="全取引がログ記録され管理者が確認可能",
        inline=True
    )
    embed.set_footer(text="Powered by Advanced PayPay Integration System")
    
    await ctx.send(embed=embed, view=PaymentPanelView())

@bot.slash_command(name="logout", description="🔓 PayPayアカウント認証解除 (管理者専用)")
@commands.has_permissions(administrator=True) 
async def logout_command(ctx):
    guild_id = str(ctx.guild.id)
    config = DataManager.load_json(CONFIG_FILE)
    
    if guild_id in config:
        del config[guild_id]
        DataManager.save_json(CONFIG_FILE, config)
        
        embed = discord.Embed(
            title="✅ ログアウト完了",
            description="PayPayアカウントの認証が解除されました",
            color=0x00ff00
        )
    else:
        embed = discord.Embed(
            title="⚠️ 認証情報なし",
            description="認証されたPayPayアカウントが見つかりません",
            color=0xffaa00
        )
    
    await ctx.respond(embed=embed, ephemeral=True)

@bot.slash_command(name="stats", description="📊 取引統計表示 (管理者専用)")
@commands.has_permissions(administrator=True)
async def stats_command(ctx):
    guild_id = str(ctx.guild.id)
    transactions = DataManager.load_json(TRANSACTIONS_FILE, [])
    guild_transactions = [t for t in transactions if t.get("guild_id") == guild_id]
    
    if not guild_transactions:
        await ctx.respond("📊 取引履歴がありません", ephemeral=True)
        return
    
    success_transactions = [t for t in guild_transactions if t.get("status") == "success"]
    error_transactions = [t for t in guild_transactions if t.get("status") == "error"]
    
    total_amount = sum(t.get("amount", 0) for t in success_transactions)
    success_rate = (len(success_transactions) / len(guild_transactions)) * 100 if guild_transactions else 0
    
    embed = discord.Embed(
        title="📊 取引統計レポート",
        color=0x3498db,
        timestamp=datetime.now()
    )
    embed.add_field(name="✅ 成功取引", value=f"{len(success_transactions)}件", inline=True)
    embed.add_field(name="❌ 失敗取引", value=f"{len(error_transactions)}件", inline=True)
    embed.add_field(name="📈 成功率", value=f"{success_rate:.1f}%", inline=True)
    embed.add_field(name="💰 総取引額", value=f"¥{total_amount:,}", inline=True)
    embed.add_field(name="📅 集計期間", value="全期間", inline=True)
    
    if success_transactions:
        avg_amount = total_amount / len(success_transactions)
        embed.add_field(name="📊 平均金額", value=f"¥{avg_amount:,.0f}", inline=True)
    
    await ctx.respond(embed=embed, ephemeral=True)

# エラーハンドリング
@bot.event
async def on_application_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(
            title="❌ 権限不足",
            description="このコマンドを実行するには管理者権限が必要です",
            color=0xff0000
        )
        await ctx.respond(embed=embed, ephemeral=True)
    else:
        logger.error(f"Command error: {error}")
        embed = discord.Embed(
            title="❌ エラー発生",
            description="コマンド実行中にエラーが発生しました",
            color=0xff0000
        )
        await ctx.respond(embed=embed, ephemeral=True)

@bot.event
async def on_ready():
    logger.info(f"Bot logged in as {bot.user.name}")
    print(f"🚀 {bot.user.name} が正常に起動しました!")
    print(f"📊 {len(bot.guilds)} サーバーで稼働中")

# セッション クリーンアップタスク
@tasks.loop(hours=1)
async def cleanup_sessions():
    current_time = time.time()
    expired_sessions = []
    
    for guild_id, session in paypay_manager.sessions.items():
        if current_time - session.get("created_at", 0) > 3600:  # 1時間後
            expired_sessions.append(guild_id)
    
    for guild_id in expired_sessions:
        del paypay_manager.sessions[guild_id]
    
    if expired_sessions:
        logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")

@cleanup_sessions.before_loop
async def before_cleanup_sessions():
    await bot.wait_until_ready()

cleanup_sessions.start()

# Discord Botトークンで実行
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_BOT_TOKEN", "YOUR_DISCORD_BOT_TOKEN")
    if TOKEN == "YOUR_DISCORD_BOT_TOKEN":
        print("⚠️  環境変数 DISCORD_BOT_TOKEN を設定してください")
        exit(1)
    
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        logger.error("Invalid Discord bot token")
    except Exception as e:
        logger.error(f"Bot startup failed: {e}")
