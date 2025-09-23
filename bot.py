import discord
from discord.ext import commands
import os
import asyncio

# Botの基本的な設定
intents = discord.Intents.default()
intents.message_content = True  # メッセージ内容を読み取るために必要
bot = commands.Bot(command_prefix='!', intents=intents)

# Bot起動時に実行される処理
@bot.event
async def on_ready():
    print(f'Logged in as: {bot.user.name}')
    print('------------------------------------------------------')
    # cogsフォルダ内の全Cogを読み込む
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
                print(f'✅ Successfully loaded: {filename}')
            except Exception as e:
                print(f'❌ Failed to load {filename}: {e}')
    print('------------------------------------------------------')
    print('Bot is now online and ready!')

# Botを起動
async def main():
    # 環境変数からDiscord Botのトークンを取得
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
