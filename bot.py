# bot.py (スラッシュコマンド同期機能付き)
import discord
from discord.ext import commands
import os
import asyncio
import google.generativeai as genai

# Botの基本的な設定
intents = discord.Intents.default()
intents.message_content = True
# '!'プレフィックスは下位互換性のために残しても良い
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

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
    
    # ★★★ 作成したスラッシュコマンドをDiscordサーバーに登録するわ ★★★
    try:
        # 全サーバーに反映（反映に最大1時間かかる場合がある）
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s).")
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")


@bot.event
async def on_ready():
    print(f'Logged in as: {bot.user.name}')
    print('Bot is now online and ready!')


@bot.event
async def on_message(message):
    if message.author.bot:
        return
    # '!'プレフィックスのコマンドも処理できるように残しておく
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
