import discord
from discord.ext import commands
import json
import os
from paypay import PayPay  # PayPaython-mobile ライブラリ

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

PAYPAY_FILE = "paypay.json"

# ヘルパー関数
def load_credentials():
    if os.path.exists(PAYPAY_FILE):
        with open(PAYPAY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_credentials(data):
    with open(PAYPAY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# Login command
@bot.slash_command(description="PayPayアカウントにログイン（管理者専用）")
@commands.has_permissions(administrator=True)
async def login(ctx, phone: str, password: str):
    guild_id = str(ctx.guild.id)
    creds = load_credentials()
    if guild_id in creds:
        await ctx.respond("⚠️ すでにログイン済みです。/logout で解除してください。", ephemeral=True)
        return

    await ctx.respond(
        "📲 認証リンクを入力するには下のボタンを押してください。",
        view=VerifyButton(phone, password, guild_id),
        ephemeral=True
    )

# Logout command
@bot.slash_command(description="PayPayログアウト（管理者専用）")
@commands.has_permissions(administrator=True)
async def logout(ctx):
    creds = load_credentials()
    guild_id = str(ctx.guild.id)
    if guild_id in creds:
        del creds[guild_id]
        save_credentials(creds)
        await ctx.respond("✅ ログアウト完了", ephemeral=True)
    else:
        await ctx.respond("⚠️ ログイン情報なし", ephemeral=True)

# Log permission command
@bot.slash_command(description="全チャンネルの表示を管理者のみに（管理者専用）")
@commands.has_permissions(administrator=True)
async def log(ctx):
    await ctx.defer(ephemeral=True)
    for ch in ctx.guild.channels:
        for role in ctx.guild.roles:
            if not role.permissions.administrator:
                await ch.set_permissions(role, view_channel=False)
            else:
                await ch.set_permissions(role, view_channel=True)
    await ctx.followup.send("✅ 管理者のみ閲覧可に設定", ephemeral=True)

class VerifyModal(discord.ui.Modal):
    def __init__(self, phone, password, guild_id):
        super().__init__(title="認証コード入力")
        self.phone = phone
        self.password = password
        self.guild_id = guild_id
        self.add_item(discord.ui.InputText(label="認証リンクまたはID", placeholder="https://paypay.ne.jp/..." or "123456"))

    async def callback(self, interaction: discord.Interaction):
        creds = load_credentials()
        try:
            paypay = PayPay(self.phone, self.password)
            paypay.login(self.children[0].value)  # 認証コードでログイン

            creds[self.guild_id] = {
                "access_token": paypay.access_token,
                "refresh_token": paypay.refresh_token,
                "device_uuid": paypay.device_uuid
            }
            save_credentials(creds)
            await interaction.response.send_message("✅ ログイン成功", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 認証失敗: {e}", ephemeral=True)

# Modal
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
            await interaction.response.send_message("❌ PayPay未ログイン", ephemeral=True)
            return
        data = creds[guild_id]
        paypay = PayPay(access_token=data["access_token"])
        try:
            info = paypay.link_check(self.children[0].value)
            if info.status != "PENDING":
                raise Exception("無効なリンク")
            paypay.link_receive(self.children[0].value, self.children[1].value or "", info)
        except Exception as e:
            await interaction.response.send_message(f"❌ エラー: {e}", ephemeral=True)
            return

        await interaction.response.send_message("✅ ご利用ありがとうございます", ephemeral=True)

        embed = discord.Embed(title="📥 支払い受領", color=0x00ff00)
        embed.add_field(name="ユーザー", value=interaction.user.mention, inline=False)
        embed.add_field(name="入力名", value=self.children[2].value, inline=False)
        embed.add_field(name="金額", value=f"{info.amount} 円", inline=False)
        embed.add_field(name="パスワード", value="あり" if info.has_password else "なし", inline=True)
        embed.add_field(name="状態", value=info.status, inline=True)
        log_channel = discord.utils.get(interaction.guild.text_channels, name="paypay-log")
        if log_channel:
            await log_channel.send(embed=embed)

# Panel View
class PanelView(discord.ui.View):
    @discord.ui.button(label="支払う", style=discord.ButtonStyle.green)
    async def button(self, button, interaction):
        await interaction.response.send_modal(PaymentModal())

# Panel command
@bot.slash_command(description="支払いパネルを表示（管理者専用）")
@commands.has_permissions(administrator=True)
async def panel(ctx):
    embed = discord.Embed(title="📦 支払いパネル", description="下のボタンから支払いリンクを入力してください。", color=0x3498db)
    await ctx.send(embed=embed, view=PanelView())

bot.run("YOUR_DISCORD_BOT_TOKEN")
