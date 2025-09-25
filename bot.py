# bot.py (最終FIX版)
import discord
from discord.ext import commands
import os
import asyncio
import google.generativeai as genai

# Botの基本的な設定
intents = discord.Intents.default()
intents.message_content = True # メッセージ内容の読み取りに必要

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

@bot.event
async def setup_hook():
    """Bot起動時にCogsを読み込み、スラッシュコマンドを同期する"""
    # Google AIモデルの設定
    api_key = os.getenv('GOOGLE_API_key')
    if not api_key:
        print("致命的エラー: GOOGLE_API_KEYが設定されていません。")
    else:
        genai.configure(api_key=api_key)
        print("Google Generative AI configured.")
    
    # cogsフォルダ内の全Cogを読み込む
    print('------------------------------------------------------')
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py') and not filename.startswith('_'):
            # データベースマネージャーは起動失敗の原因のため、一時的に無効化
            if filename == 'database_manager.py':
                print(f'⚠️  {filename} は既知の問題により、一時的に読み込みをスキップします。')
                continue
            
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
                print(f'✅ Successfully loaded: {filename}')
            except Exception as e:
                print(f'❌ Failed to load {filename}: {e.__class__.__name__}: {e}')
    print('------------------------------------------------------')
    
    # スラッシュコマンドをDiscordサーバーに登録
    try:
        synced = await bot.tree.sync()
        if synced:
            print(f"Synced {len(synced)} slash command(s).")
        else:
            print("No new slash commands to sync.")
            
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")

@bot.event
async def on_ready():
    """Botのログインが完了したときに呼び出される"""
    print('------------------------------------------------------')
    print(f'Logged in as: {bot.user.name} (ID: {bot.user.id})')
    print('Bot is now online and ready!')
    print('------------------------------------------------------')

async def main():
    """Botを起動するメイン処理"""
    token = os.getenv('DISCORD_BOT_TOKEN')
    if token is None:
        print("致命的エラー: DISCORD_BOT_TOKENが環境変数に設定されていません。")
        return
    
    async with bot:
        await bot.start(token)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot is shutting down...")
