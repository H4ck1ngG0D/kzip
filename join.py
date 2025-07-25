import discord
from discord import app_commands
from discord.ext import tasks
import requests
import aiohttp
import asyncio
import random
import re
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
async def validate_token(token, proxy=None):
    headers = {'Authorization': token}
    async with aiohttp.ClientSession() as session:
        # Try without proxy first
        try:
            async with session.get('https://discord.com/api/v10/users/@me', headers=headers, timeout=3) as response:
                if response.status == 200:
                    return True, "Token validated successfully without proxy."
                else:
                    error_msg = f"Failed without proxy: {response.status} {await response.text()[:100]}"
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            error_msg = f"Failed without proxy: {str(e)}"

        # If proxy is provided, try with proxy
        if proxy:
            try:
                async with session.get('https://discord.com/api/v10/users/@me', headers=headers, proxy=proxy, timeout=3) as response:
                    if response.status == 200:
                        return True, f"Token validated successfully with proxy {proxy}."
                    else:
                        return False, f"{error_msg} | Failed with proxy: {response.status} {await response.text()[:100]}"
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                return False, f"{error_msg} | Failed with proxy: {str(e)}"
        return False, error_msg

# Join server using a token, invite code, and optional proxy
async def join_server(token, invite_code, proxy=None):
    headers = {
        'Authorization': token,
        'Content-Type': 'application/json'
    }
    api_url = f"https://discord.com/api/v10/invites/{invite_code}"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(api_url, headers=headers, data='{}', proxy=proxy, timeout=3) as response:
                if response.status == 200:
                    join_logs['joined'] += 1
                    return "joined", "Joined successfully."
                elif response.status == 403 and 'captcha' in (await response.text()).lower():
                    join_logs['captcha'] += 1
                    return "captcha", "Failed due to CAPTCHA."
                else:
                    join_logs['failed'] += 1
                    return "failed", f"Failed: {response.status} {await response.text()[:100]}"
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            join_logs['failed'] += 1
            return "failed", f"Failed: {str(e)}"

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

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if isinstance(message.channel, discord.DMChannel):
        # Handle !join command
        if message.content.startswith('!join'):
            match = re.search(r'(?:https?://)?discord\.gg/([a-zA-Z0-9-]+)|([a-zA-Z0-9-]+)', message.content)
            if not match:
                await message.channel.send("Invalid invite link. Use discord.gg/strk, https://discord.gg/strk, or strk.")
                return
            invite_code = match.group(1) or match.group(2)
            user_id = message.author.id

            if user_id not in user_tokens or not user_tokens[user_id]:
                await message.channel.send("You have no saved tokens. Send tokens or token.txt in DM.")
                return

            results = []
            successful_tokens = []
            for token in user_tokens[user_id]:
                proxy = None
                if user_id not in user_proxy_setting or user_proxy_setting[user_id] == 'iproyal':
                    proxy = random.choice(IPROYAL_PROXIES)
                elif user_proxy_setting.get(user_id) == 'custom' and user_id in user_proxies:
                    proxy = random.choice(user_proxies[user_id])

                result, details = await join_server(token, invite_code, proxy)
                results.append(f"Token attempt: {result} ({details})")
                if result == "joined":
                    successful_tokens.append(token)
                await asyncio.sleep(0.5)  # 0.5-second delay between requests

            # Send results and logs
            await message.channel.send("\n".join(results))
            log_message = f"joined {join_logs['joined']}\ncaptcha {join_logs['captcha']}\nfailed {join_logs['failed']}"
            await message.channel.send(log_message)
            if successful_tokens:
                save_successful_tokens(successful_tokens)
                await message.channel.send(f"Successful tokens:\n" + "\n".join(successful_tokens))

        # Handle token or proxy submission
        if message.attachments:
            for attachment in message.attachments:
                if attachment.filename.endswith('.txt'):
                    content = await attachment.read()
                    lines = content.decode('utf-8').splitlines()
                    if not lines:
                        await message.channel.send("Empty file.")
                        return

                    # Determine if it's a token or proxy file
                    first_line = next((line.strip() for line in lines if line.strip()), "")
                    is_proxy = first_line.startswith('http') or re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', first_line)
                    user_id = message.author.id

                    if is_proxy:
                        valid_proxies = []
                        invalid_count = 0
                        async def validate_proxy(proxy):
                            try:
                                async with aiohttp.ClientSession() as session:
                                    async with session.get('https://api.ipify.org', proxy=proxy, timeout=3) as response:
                                        return proxy if response.status == 200 else None
                            except (aiohttp.ClientError, asyncio.TimeoutError):
                                return None

                        for i in range(0, len(lines), 10):
                            batch = [p.strip() for p in lines[i:i+10] if p.strip()]
                            tasks = [validate_proxy(proxy) for proxy in batch]
                            results = await asyncio.gather(*tasks, return_exceptions=True)
                            valid_proxies.extend([r for r in results if r is not None])
                            invalid_count += len(batch) - len([r for r in results if r is not None])

                        user_proxies[user_id] = valid_proxies
                        user_proxy_setting[user_id] = 'custom'
                        await message.channel.send(
                            f"Loaded {len(valid_proxies)} valid proxies. {invalid_count} invalid proxies skipped."
                        )
                    else:
                        valid_tokens = []
                        invalid_count = 0
                        proxy = random.choice(IPROYAL_PROXIES) if user_id not in user_proxy_setting or user_proxy_setting[user_id] == 'iproyal' else None
                        if user_proxy_setting.get(user_id) == 'custom' and user_id in user_proxies:
                            proxy = random.choice(user_proxies[user_id])

                        for token in lines:
                            token = token.strip()
                            if token and token not in user_tokens.get(user_id, []):
                                is_valid, _ = await validate_token(token, proxy)
                                if is_valid:
                                    if user_id not in user_tokens:
                                        user_tokens[user_id] = []
                                    user_tokens[user_id].append(token)
                                    valid_tokens.append(token)
                                else:
                                    invalid_count += 1
                            else:
                                invalid_count += 1

                        await message.channel.send(
                            f"Loaded {len(valid_tokens)} valid tokens. {invalid_count} invalid or duplicate tokens skipped."
                        )
        elif message.content:
            # Handle tokens sent directly in message
            tokens = message.content.splitlines()
            valid_tokens = []
            invalid_count = 0
            user_id = message.author.id
            proxy = random.choice(IPROYAL_PROXIES) if user_id not in user_proxy_setting or user_proxy_setting[user_id] == 'iproyal' else None
            if user_proxy_setting.get(user_id) == 'custom' and user_id in user_proxies:
                proxy = random.choice(user_proxies[user_id])

            for token in tokens:
                token = token.strip()
                if token and token.startswith('M') and token not in user_tokens.get(user_id, []):
                    is_valid, error_message = await validate_token(token, proxy)
                    if is_valid:
                        if user_id not in user_tokens:
                            user_tokens[user_id] = []
                        user_tokens[user_id].append(token)
                        valid_tokens.append(token)
                    else:
                        invalid_count += 1
                        await message.channel.send(f"Token invalid: {error_message}")
                else:
                    invalid_count += 1

            if valid_tokens:
                await message.channel.send(
                    f"Loaded {len(valid_tokens)} valid tokens. {invalid_count} invalid or duplicate tokens skipped."
                )

    await bot.process_commands(message)

@app_commands.command(name="savetoken", description="Save a single Discord token for joining servers")
async def savetoken(interaction: discord.Interaction, token: str):
    user_id = interaction.user.id
    if user_id not in user_tokens:
        user_tokens[user_id] = []

    proxy = random.choice(IPROYAL_PROXIES) if user_id not in user_proxy_setting or user_proxy_setting[user_id] == 'iproyal' else None
    if user_proxy_setting.get(user_id) == 'custom' and user_id in user_proxies:
        proxy = random.choice(user_proxies[user_id])

    is_valid, error_message = await validate_token(token, proxy)
    if is_valid:
        if token not in user_tokens[user_id]:
            user_tokens[user_id].append(token)
            await interaction.response.send_message(
                f"Token saved successfully! You have {len(user_tokens[user_id])} tokens saved. ({error_message})",
                ephemeral=True
            )
        else:
            await interaction.response.send_message("This token is already saved.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Error: Invalid or expired token. Details: {error_message}", ephemeral=True)

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
                if token and token not in user_tokens[user_id]:
                    is_valid, _ = await validate_token(token, proxy)
                    if is_valid:
                        user_tokens[user_id].append(token)
                        valid_tokens.append(token)
                    else:
                        invalid_count += 1
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
            valid_proxies = []
            invalid_count = 0

            # Validate proxies asynchronously with limited concurrency
            async def validate_proxy(proxy):
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get('https://api.ipify.org', proxy=proxy, timeout=3) as response:
                            return proxy if response.status == 200 else None
                except (aiohttp.ClientError, asyncio.TimeoutError):
                    return None

            # Process proxies in batches of 10
            for i in range(0, len(proxies), 10):
                batch = [p.strip() for p in proxies[i:i+10] if p.strip()]
                tasks = [validate_proxy(proxy) for proxy in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                valid_proxies.extend([r for r in results if r is not None])
                invalid_count += len(batch) - len([r for r in results if r is not None])

            user_proxies[user_id] = valid_proxies
            user_proxy_setting[user_id] = 'custom'
            await interaction.response.send_message(
                f"Loaded {len(valid_proxies)} valid proxies. {invalid_count} invalid proxies skipped.",
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
    match = re.search(r'(?:https?://)?discord\.gg/([a-zA-Z0-9-]+)|([a-zA-Z0-9-]+)', invite_link)
    if not match:
        await interaction.response.send_message("Invalid invite link. Use discord.gg/strk, https://discord.gg/strk, or strk.", ephemeral=True)
        return
    invite_code = match.group(1) or match.group(2)
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

        result, details = await join_server(token, invite_code, proxy)
        results.append(f"Token attempt: {result} ({details})")
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
            is_valid, _ = await validate_token(token, proxy)
            if is_valid:
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
