import discord
from discord.ext import commands
import json
import os
from PayPaython_mobile import PayPay

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

PAYPAY_FILE = "paypay.json"

# 認証情報のロード・保存
def load_credentials():
    if os.path.exists(PAYPAY_FILE):
        with open(PAYPAY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_credentials(data):
    with open(PAYPAY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# /login コマンド
@bot.slash_command(description="PayPayアカウントにログイン（ステップ1）")
@commands.has_permissions(administrator=True)
async def login(ctx, phone: str, password: str):
    await ctx.defer(ephemeral=True)
    guild_id = str(ctx.guild.id)
    creds = load_credentials()
    if guild_id in creds:
        await ctx.respond("⚠️ すでにログイン済みです。/logout で解除してください。", ephemeral=True)
        return

    try:
        paypay = PayPay(phone, password)
        login_id = paypay.get_login_id()  # 認証リンクまたはID取得

        # 電話番号とパスワードを一時保存
        creds[guild_id] = {
            "phone": phone,
            "password": password,
            "login_id": login_id
        }
        save_credentials(creds)

        # 認証IDを送信
        await ctx.respond(
            f"📨 認証リンクが送信されました！SMSを確認してください。\n"
            f"```認証ID: {login_id}```",
            ephemeral=True
        )

        # 認証リンクパネルを追加で送信（ここがあなたの指摘）
        await ctx.followup.send(
            "👇 認証リンクまたはコードを入力してください。",
            view=VerifyButton(phone, password, guild_id),
            ephemeral=True
        )

    except Exception as e:
        await ctx.respond(f"❌ 初期化失敗: {e}", ephemeral=True)


# Verify モーダル
class VerifyModal(discord.ui.Modal):
    def __init__(self, phone, password, guild_id):
        super().__init__(title="認証コード入力")
        self.phone = phone
        self.password = password
        self.guild_id = guild_id
        self.add_item(discord.ui.InputText(label="認証リンクまたはID", placeholder="https://paypay.ne.jp/..."))

    async def callback(self, interaction: discord.Interaction):
        creds = load_credentials()
        try:
            paypay = PayPay(self.phone, self.password)
            paypay.login(self.children[0].value)  # 認証リンクを渡してログイン

            creds[self.guild_id] = {
                "access_token": paypay.access_token,
                "refresh_token": paypay.refresh_token,
                "device_uuid": paypay.device_uuid
            }
            save_credentials(creds)
            await interaction.response.send_message("✅ ログイン成功", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 認証失敗: {e}", ephemeral=True)

# Verifyボタン
class VerifyButton(discord.ui.View):
    def __init__(self, phone, password, guild_id):
        super().__init__()
        self.phone = phone
        self.password = password
        self.guild_id = guild_id

    @discord.ui.button(label="認証リンクを入力", style=discord.ButtonStyle.primary)
    async def verify(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_modal(VerifyModal(self.phone, self.password, self.guild_id))

# /logout コマンド
@bot.slash_command(description="PayPayからログアウト（管理者専用）")
@commands.has_permissions(administrator=True)
async def logout(ctx):
    creds = load_credentials()
    guild_id = str(ctx.guild.id)
    if guild_id in creds:
        del creds[guild_id]
        save_credentials(creds)
        await ctx.respond("✅ ログアウトしました。", ephemeral=True)
    else:
        await ctx.respond("⚠️ ログイン情報が見つかりません。", ephemeral=True)

# /log コマンド：チャンネルを管理者専用に
@bot.slash_command(description="全チャンネルを管理者のみに制限（管理者専用）")
@commands.has_permissions(administrator=True)
async def log(ctx):
    await ctx.defer(ephemeral=True)
    for ch in ctx.guild.channels:
        for role in ctx.guild.roles:
            if not role.permissions.administrator:
                await ch.set_permissions(role, view_channel=False)
            else:
                await ch.set_permissions(role, view_channel=True)
    await ctx.followup.send("✅ 全チャンネルを管理者専用に変更しました。", ephemeral=True)

# 支払いフォーム
class PaymentModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="支払いフォーム")
        self.add_item(discord.ui.InputText(label="PayPayリンク", placeholder="https://paypay.ne.jp/..."))
        self.add_item(discord.ui.InputText(label="パスワード（任意）", required=False))
        self.add_item(discord.ui.InputText(label="ユーザー名", placeholder="山田太郎"))

    async def callback(self, interaction: discord.Interaction):
        creds = load_credentials()
        guild_id = str(interaction.guild.id)
        if guild_id not in creds:
            await interaction.response.send_message("❌ PayPay未ログインです。", ephemeral=True)
            return

        data = creds[guild_id]
        paypay = PayPay(access_token=data["access_token"])
        try:
            info = paypay.link_check(self.children[0].value)
            if info.status != "PENDING":
                raise Exception("無効なリンクです。")
            paypay.link_receive(self.children[0].value, self.children[1].value or "", info)
        except Exception as e:
            await interaction.response.send_message(f"❌ エラー: {e}", ephemeral=True)
            return

        await interaction.response.send_message("✅ ご利用ありがとうございました。", ephemeral=True)

        embed = discord.Embed(title="📥 支払い受領", color=0x00ff00)
        embed.add_field(name="ユーザー", value=interaction.user.mention, inline=False)
        embed.add_field(name="入力名", value=self.children[2].value, inline=False)
        embed.add_field(name="金額", value=f"{info.amount} 円", inline=False)
        embed.add_field(name="パスワード", value="あり" if info.has_password else "なし", inline=True)
        embed.add_field(name="状態", value=info.status, inline=True)

        log_channel = discord.utils.get(interaction.guild.text_channels, name="paypay-log")
        if log_channel:
            await log_channel.send(embed=embed)

# パネルボタン
class PanelView(discord.ui.View):
    @discord.ui.button(label="支払う", style=discord.ButtonStyle.green)
    async def button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_modal(PaymentModal())

# /panel コマンド
@bot.slash_command(description="支払いパネルを表示（管理者専用）")
@commands.has_permissions(administrator=True)
async def panel(ctx):
    embed = discord.Embed(title="📦 支払いパネル", description="下のボタンから支払いを行えます。", color=0x3498db)
    await ctx.send(embed=embed, view=PanelView())

# 実行
bot.run("YOUR_DISCORD_BOT_TOKEN")
