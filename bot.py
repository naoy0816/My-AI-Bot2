# bot.py (最終修正版)
import discord
from discord.ext import commands
import os
import asyncio
import google.generativeai as genai # ★★★ 追加 ★★★

# Botの基本的な設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# ★★★ ここで最初に一回だけ、AIに挨拶するのよ！ ★★★
@bot.event
async def setup_hook():
    # GoogleのAIモデルを設定
    genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
    print("Google Generative AI configured.")
    # cogsフォルダ内の全Cogを読み込む
    print('------------------------------------------------------')
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py') and not filename.startswith('_'):
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
                print(f'✅ Successfully loaded: {filename}')
            except Exception as e:
                print(f'❌ Failed to load {filename}: {e}')
    print('------------------------------------------------------')


@bot.event
async def on_ready():
    print(f'Logged in as: {bot.user.name}')
    print('Bot is now online and ready!')


@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)

# Botを起動
async def main():
    token = os.getenv('DISCORD_BOT_TOKEN')
    if token is None:
        print("Error: DISCORD_BOT_TOKEN is not set in environment variables.")
        return
    
    async with bot:
        await bot.start(token)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot is shutting down...")
