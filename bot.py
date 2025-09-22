# bot.py (最終完全版)
import discord
from discord.ext import commands
import os

# ▼▼▼ キーは環境変数から読み込む！ ▼▼▼
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
# ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

# ボットの基本設定
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

# 起動時にCog（機能別ファイル）を読み込む
@bot.event
async def on_ready():
    print(f'Bot logged in as {bot.user}')
    print('------')
    for filename in os.listdir('./cogs'):
        # ▼▼▼ keywords.py を読み込まないように修正 ▼▼▼
        if filename.endswith('.py') and filename != 'keywords.py':
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
                print(f'Loaded cog: {filename}')
            except Exception as e:
                print(f'Failed to load cog {filename}: {e}')

# ボットを実行
if __name__ == '__main__':
    if not DISCORD_BOT_TOKEN or not GOOGLE_API_KEY:
        print("エラー: DISCORD_BOT_TOKENまたはGOOGLE_API_KEYが設定されていません。")
    else:
        bot.run(DISCORD_BOT_TOKEN)
