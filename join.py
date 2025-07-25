import discord
from discord import app_commands
from discord.ext import tasks
import requests
import asyncio
import random
from datetime import datetime

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# Token storage (in-memory for simplicity; use a database for production)
user_tokens = {}  # {user_id: [token1, token2, ...]}
user_proxies = {}  # {user_id: [proxy1, proxy2, ...]}
user_proxy_setting = {}  # {user_id: 'iproyal' or 'none' or 'custom'}

# Logging storage
join_logs = {'joined': 0, 'captcha': 0, 'failed': 0}

# IPRoyal free proxies (example list; replace with actual proxies from IPRoyal)
IPROYAL_PROXIES = [
    "http://190.104.146.244:999",
    "http://140.246.149.224:8888",
    "http://140.246.149.224:8888101.255.94.161:8080",
    # Add actual IPRoyal free proxy URLs here
]

# Validate token by checking if it can fetch user info
def validate_token(token, proxy=None):
    headers = {'Authorization': token}
    proxies = {'http': proxy, 'https': proxy} if proxy else None
    try:
        response = requests.get('https://discord.com/api/v10/users/@me', headers=headers, proxies=proxies, timeout=10)
        return response.status_code == 200
    except requests.RequestException:
        return False

# Join server using a token, invite code, and optional proxy
def join_server(token, invite_code, proxy=None):
    headers = {
        'Authorization': token,
        'Content-Type': 'application/json'
    }
    api_url = f"https://discord.com/api/v10/invites/{invite_code}"
    proxies = {'http': proxy, 'https': proxy} if proxy else None
    try:
        response = requests.post(api_url, headers=headers, data='{}', proxies=proxies, timeout=10)
        if response.status_code == 200:
            join_logs['joined'] += 1
            return "joined"
        elif response.status_code == 403 and 'captcha' in response.text.lower():
            join_logs['captcha'] += 1
            return "captcha"
        else:
            join_logs['failed'] += 1
            return f"failed: {response.status_code}"
    except requests.RequestException as e:
        join_logs['failed'] += 1
        return f"failed: {str(e)}"

# Save successful tokens to a file
def save_successful_tokens(tokens):
    with open('successfully.txt', 'a') as f:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for token in tokens:
            f.write(f"[{timestamp}] {token}\n")

@bot.event
async def on_ready():
    print(f'Bot is ready as {bot.user}')
    await tree.sync()  # Sync slash commands
    check_tokens.start()  # Start the hourly token check

@app_commands.command(name="savetoken", description="Save a single Discord token for joining servers")
async def savetoken(interaction: discord.Interaction, token: str):
    user_id = interaction.user.id
    if user_id not in user_tokens:
        user_tokens[user_id] = []

    proxy = random.choice(IPROYAL_PROXIES) if user_id not in user_proxy_setting or user_proxy_setting[user_id] == 'iproyal' else None
    if user_proxy_setting.get(user_id) == 'custom' and user_id in user_proxies:
        proxy = random.choice(user_proxies[user_id])

    if validate_token(token, proxy):
        if token not in user_tokens[user_id]:
            user_tokens[user_id].append(token)
            await interaction.response.send_message(
                f"Token saved successfully! You have {len(user_tokens[user_id])} tokens saved.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message("This token is already saved.", ephemeral=True)
    else:
        await interaction.response.send_message("Error: Invalid or expired token.", ephemeral=True)

@app_commands.command(name="loadtokenfile", description="Load multiple tokens from a .txt file")
async def loadtokenfile(interaction: discord.Interaction, file: discord.Attachment):
    user_id = interaction.user.id
    if user_id not in user_tokens:
        user_tokens[user_id] = []

    if file.filename.endswith('.txt'):
        try:
            content = await file.read()
            tokens = content.decode('utf-8').splitlines()
            valid_tokens = []
            invalid_count = 0
            proxy = random.choice(IPROYAL_PROXIES) if user_id not in user_proxy_setting or user_proxy_setting[user_id] == 'iproyal' else None
            if user_proxy_setting.get(user_id) == 'custom' and user_id in user_proxies:
                proxy = random.choice(user_proxies[user_id])

            for token in tokens:
                token = token.strip()
                if token and token not in user_tokens[user_id] and validate_token(token, proxy):
                    user_tokens[user_id].append(token)
                    valid_tokens.append(token)
                else:
                    invalid_count += 1

            await interaction.response.send_message(
                f"Loaded {len(valid_tokens)} valid tokens. {invalid_count} invalid or duplicate tokens skipped.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"Error reading file: {str(e)}", ephemeral=True)
    else:
        await interaction.response.send_message("Please upload a .txt file.", ephemeral=True)

@app_commands.command(name="proxyload", description="Load proxies from a .txt file")
async def proxyload(interaction: discord.Interaction, file: discord.Attachment):
    user_id = interaction.user.id
    if file.filename.endswith('.txt'):
        try:
            content = await file.read()
            proxies = content.decode('utf-8').splitlines()
            valid_proxies = [p.strip() for p in proxies if p.strip()]
            user_proxies[user_id] = valid_proxies
            user_proxy_setting[user_id] = 'custom'
            await interaction.response.send_message(
                f"Loaded {len(valid_proxies)} proxies. Using custom proxies for your requests.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"Error reading file: {str(e)}", ephemeral=True)
    else:
        await interaction.response.send_message("Please upload a .txt file.", ephemeral=True)

@app_commands.command(name="proxynone", description="Disable proxies for your requests")
async def proxynone(interaction: discord.Interaction):
    user_id = interaction.user.id
    user_proxy_setting[user_id] = 'none'
    await interaction.response.send_message("Proxies disabled for your requests.", ephemeral=True)

@app_commands.command(name="join", description="Join a server using saved tokens and an invite link")
async def join(interaction: discord.Interaction, invite_link: str):
    invite_code = invite_link.split('/')[-1]
    user_id = interaction.user.id

    if user_id not in user_tokens or not user_tokens[user_id]:
        await interaction.response.send_message(
            "You have no saved tokens. Use /savetoken or /loadtokenfile to save tokens first.",
            ephemeral=True
        )
        return

    results = []
    successful_tokens = []
    for token in user_tokens[user_id]:
        proxy = None
        if user_id not in user_proxy_setting or user_proxy_setting[user_id] == 'iproyal':
            proxy = random.choice(IPROYAL_PROXIES)
        elif user_proxy_setting.get(user_id) == 'custom' and user_id in user_proxies:
            proxy = random.choice(user_proxies[user_id])

        result = join_server(token, invite_code, proxy)
        results.append(f"Token attempt: {result}")
        if result == "joined":
            successful_tokens.append(token)
        await asyncio.sleep(0.5)  # 0.5-second delay between requests

    # Send join attempt results as ephemeral message
    await interaction.response.send_message("\n".join(results), ephemeral=True)
    
    # Send logs as ephemeral message in the requested format
    log_message = f"joined {join_logs['joined']}\ncaptcha {join_logs['captcha']}\nfailed {join_logs['failed']}"
    await interaction.followup.send(log_message, ephemeral=True)
    
    # Save successful tokens to file and send as ephemeral message
    if successful_tokens:
        save_successful_tokens(successful_tokens)
        await interaction.followup.send(f"Successful tokens:\n" + "\n".join(successful_tokens), ephemeral=True)

@tasks.loop(hours=1)
async def check_tokens():
    for user_id, tokens in list(user_tokens.items()):
        valid_tokens = []
        proxy = random.choice(IPROYAL_PROXIES) if user_id not in user_proxy_setting or user_proxy_setting[user_id] == 'iproyal' else None
        if user_proxy_setting.get(user_id) == 'custom' and user_id in user_proxies:
            proxy = random.choice(user_proxies[user_id])
        for token in tokens:
            if validate_token(token, proxy):
                valid_tokens.append(token)
            else:
                print(f"Token invalid for user {user_id}")
        user_tokens[user_id] = valid_tokens
        if not valid_tokens:
            del user_tokens[user_id]

# Register commands
tree.add_command(savetoken)
tree.add_command(loadtokenfile)
tree.add_command(proxyload)
tree.add_command(proxynone)
tree.add_command(join)

# Replace 'YOUR_BOT_TOKEN' with your actual bot token
bot.run('YOUR_BOT_TOKEN')
