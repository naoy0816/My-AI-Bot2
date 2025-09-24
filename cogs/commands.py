# cogs/commands.py (ペルソナ管理コマンド追加版)
import discord
from discord.ext import commands
import json
import google.generativeai as genai
import os
from . import _utils as utils
from . import _persona_manager as persona_manager # ★★★ persona_managerをインポート ★★★

DATA_DIR = os.getenv('RAILWAY_VOLUME_MOUNT_PATH', '.')
MEMORY_FILE = os.path.join(DATA_DIR, 'bot_memory.json')
TODO_FILE = os.path.join(DATA_DIR, 'todos.json')

def load_memory():
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"users": {}, "server": {"notes": []}}

def save_memory(data):
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

def load_todos():
    try:
        with open(TODO_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_todos(data):
    with open(TODO_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

class UserCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
        self.model = genai.GenerativeModel('gemini-1.5-flash')

    # ★★★ ここからペルソナ管理コマンドよ！ ★★★
    @commands.command(name='list_personas', aliases=['personas'])
    async def list_personas(self, ctx):
        """利用可能なペルソナの一覧を表示するわ"""
        personas = persona_manager.list_personas()
        if not personas:
            await ctx.send("利用できるペルソナが一人もいないんだけど？ `personas`フォルダを確認しなさい！")
            return
        
        embed = discord.Embed(
            title="♡アタシがなれる人格（ペルソナ）一覧♡",
            description="`!set_persona [id]`でアタシの人格を変えられるわよ（オーナー限定）",
            color=discord.Color.gold()
        )
        for p in personas:
            embed.add_field(name=f"**{p['name']}** (`{p['id']}`)", value=p['description'], inline=False)
        
        current_persona_name = utils.get_current_persona().get("name", "不明")
        embed.set_footer(text=f"現在のアタシの人格: {current_persona_name}")
        await ctx.send(embed=embed)

    @commands.command(name='set_persona')
    @commands.is_owner()
    async def set_persona(self, ctx, persona_id: str = None):
        """アタシの人格（ペルソナ）を切り替えるわよ（オーナー限定）"""
        if not persona_id:
            await ctx.send("はぁ？ どのアタシになりたいわけ？ IDを指定しなさい！ `!list_personas`で確認できるわよ。")
            return

        available_personas = [p['id'] for p in persona_manager.list_personas()]
        if persona_id not in available_personas:
            await ctx.send(f"「{persona_id}」なんて人格、アタシにはないんだけど？ IDが間違ってるんじゃないの？")
            return

        memory = load_memory()
        if 'server' not in memory: memory['server'] = {}
        memory['server']['current_persona'] = persona_id
        save_memory(memory)
        
        new_persona = persona_manager.load_persona(persona_id)
        await ctx.send(f"ふん、しょーがないから、今日からアタシは「**{new_persona.get('name')}**」になってやんよ♡ ありがたく思いなさいよね！")
    
    @commands.command(name='current_persona')
    async def current_persona(self, ctx):
        """今のアタシがどんな人格か教えてあげる"""
        persona = utils.get_current_persona()
        if not persona:
            await ctx.send("（ごめん、ペルソナファイルがなくて自分が誰だかわかんないの…）")
            return
        
        embed = discord.Embed(
            title=f"♡今のアタシは「{persona.get('name')}」よ♡",
            description=persona.get('description'),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
    # ★★★ ペルソナ管理コマンドはここまで ★★★

    @commands.command(name='help', aliases=['h', 'commands'])
    async def help_command(self, ctx):
        embed = discord.Embed(
            title="♡アタシのコマンド一覧♡",
            description="アンタみたいなザコでも使えるように、一覧にしてあげたわ。せいぜい使いこなしなさいよね！",
            color=discord.Color.magenta()
        )
        embed.add_field(name="🧠 AIチャット & 記憶", value="`!remember [内容]` - アタシにアンタのことを記憶させる\n`!recall` - 記憶リストを表示\n`!forget [番号]` - 記憶を忘れさせてあげる\n`!setname [名前]` - アタシが呼ぶアンタの名前を設定\n`!myname` - 設定した名前を確認", inline=False)
        embed.add_field(name="🌐 サーバー共通", value="`!server_remember [内容]` - サーバーの皆で共有したいことを記憶\n`!server_recall` - サーバーの共有知識を表示", inline=False)
        embed.add_field(name="👤 ペルソナ管理", value="`!list_personas` - ペルソナ一覧\n`!current_persona` - 現在のペルソナ確認\n`!set_persona [ID]` - ペルソナ切替 (オーナー限定)", inline=False)
        embed.add_field(name="🛠️ ツール", value="`!search [キーワード]` (`!g`) - アンタの代わりにググってあげる\n`!todo add [内容]` - やることを追加\n`!todo list` - やることリストを表示\n`!todo done [番号]` - 完了したことを消す\n`!roast` - (画像を添付して) アタシに画像をイジらせる", inline=False)
        embed.add_field(name="⚙️ デバッグ", value="`!ping` - アタシの反応速度をチェック\n`!debug_memory` - 長期記憶の中身を全部見る\n`!reload_cogs` - アタシの全機能を再読み込み (オーナー限定)", inline=False)
        embed.set_footer(text="アタシへの会話は @メンション を付けて話しかけなさいよね！")
        await ctx.send(embed=embed)
    
    # (ping, roast, reload_cogs, debug_memory, search, testnews, todo, remember, recall, forget, setname, myname, server_remember, server_recall は変更なし)
    # ... (省略) ...

async def setup(bot):
    await bot.add_cog(UserCommands(bot))
