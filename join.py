import discord
from discord import app_commands
from discord.ext import tasks
import requests
import asyncio
from datetime import datetime

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# Token storage (in-memory for simplicity; use a database for production)
user_tokens = {}  # {user_id: [token1, token2, ...]}

# Logging storage
join_logs = {'joined': 0, 'captcha': 0, 'failed': 0}

# Validate token by checking if it can fetch user info
def validate_token(token):
    headers = {'Authorization': token}
    response = requests.get('https://discord.com/api/v10/users/@me', headers=headers)
    return response.status_code == 200

# Join server using a token and invite code
def join_server(token, invite_code):
    headers = {
        'Authorization': token,
        'Content-Type': 'application/json'
    }
    api_url = f"https://discord.com/api/v10/invites/{invite_code}"
    response = requests.post(api_url, headers=headers, data='{}')
    
    if response.status_code == 200:
        join_logs['joined'] += 1
        return "joined"
    elif response.status_code == 403 and 'captcha' in response.text.lower():
        join_logs['captcha'] += 1
        return "captcha"
    else:
        join_logs['failed'] += 1
        return "failed"

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

@app_commands.command(name="savetoken", description="Save a Discord token for joining servers")
async def savetoken(interaction: discord.Interaction, token: str):
    user_id = interaction.user.id
    if user_id not in user_tokens:
        user_tokens[user_id] = []

    if validate_token(token):
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

@app_commands.command(name="join", description="Join a server using saved tokens and an invite link")
async def join(interaction: discord.Interaction, invite_link: str):
    invite_code = invite_link.split('/')[-1]
    user_id = interaction.user.id

    if user_id not in user_tokens or not user_tokens[user_id]:
        await interaction.response.send_message(
            "You have no saved tokens. Use /savetoken to save a token first.",
            ephemeral=True
        )
        return

    results = []
    successful_tokens = []
    for token in user_tokens[user_id]:
        result = join_server(token, invite_code)
        results.append(f"Token attempt: {result}")
        if result == "joined":
            successful_tokens.append(token)
    
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
        for token in tokens:
            if validate_token(token):
                valid_tokens.append(token)
            else:
                # Notify user of invalid token (simplified; in production, use a specific channel or DM)
                print(f"Token invalid for user {user_id}")
        user_tokens[user_id] = valid_tokens
        if not valid_tokens:
            del user_tokens[user_id]

# Register commands
tree.add_command(savetoken)
tree.add_command(join)

# Replace 'YOUR_BOT_TOKEN' with your actual bot token
bot.run('YOUR_BOT_TOKEN')
