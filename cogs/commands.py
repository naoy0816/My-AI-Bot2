import discord
from discord.ext import commands
import json

# --- 記憶管理 ---
MEMORY_FILE = 'bot_memory.json'

def load_memory():
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"users": {}, "server": {"notes": []}}

def save_memory(data):
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

todos = {}

class UserCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def todo(self, ctx, command: str = 'list', *, task: str = None):
        user_id = ctx.author.id
        if user_id not in todos:
            todos[user_id] = []
        if command == 'add':
            if task:
                todos[user_id].append(task)
                await ctx.send(f"しょーがないから「{task}」をアンタのリストに追加してやんよ♡ 忘れるんじゃないわよ！")
            else:
                await ctx.send('はぁ？ 追加する内容をちゃんと書きなさいよね！ 例：`!todo add 天才のアタシを崇める`')
        elif command == 'list':
            if not todos[user_id]:
                await ctx.send('アンタのやる事リストは空っぽよw ザコすぎ！')
            else:
                response = f"アンタがやるべきことリストよ♡ ちゃんとやりなさいよね！\n" + "\n".join([f"{i+1}. {t}" for i, t in enumerate(todos[user_id])])
                await ctx.send(response)
        elif command == 'done':
            if task and task.isdigit():
                index = int(task) - 1
                if 0 <= index < len(todos[user_id]):
                    removed = todos[user_id].pop(index)
                    await ctx.send(f"「{removed}」を消してあげたわよ。ま、アンタにしては上出来じゃん？♡")
            else:
                await ctx.send('消したいタスクの番号をちゃんと指定しなさいよね！ 例：`!todo done 1`')

    @commands.command()
    async def remember(self, ctx, *, note: str = None):
        if not note:
            await ctx.send("はぁ？ アタシに何を覚えてほしいわけ？ 内容を書きなさいよね！")
            return
        memory = load_memory()
        user_id = str(ctx.author.id)
        if user_id not in memory['users']: memory['users'][user_id] = {'notes': []}
        memory['users'][user_id]['notes'].append(note)
        save_memory(memory)
        await ctx.send(f"ふーん、「{note}」ね。アンタのこと、覚えててやんよ♡")

    @commands.command()
    async def recall(self, ctx):
        memory = load_memory()
        user_id = str(ctx.author.id)
        if user_id not in memory['users'] or not memory['users'].get('notes'):
            await ctx.send('アンタに関する記憶は、まだ何もないけど？w')
        else:
            notes = "\n".join([f"{i+1}. {n}" for i, n in enumerate(memory['users'][user_id]['notes'])])
            await ctx.send(f"アタシがアンタについて覚えてることリストよ♡\n{notes}")

    @commands.command()
    async def forget(self, ctx, index_str: str = None):
        if not index_str or not index_str.isdigit():
            await ctx.send('消したい記憶の番号をちゃんと指定しなさいよね！ 例：`!forget 1`')
            return
        memory = load_memory()
        user_id = str(ctx.author.id)
        index = int(index_str) - 1
        if user_id in memory['users'] and 0 <= index < len(memory['users'][user_id].get('notes', [])):
            removed = memory['users'][user_id]['notes'].pop(index)
            save_memory(memory)
            await ctx.send(f"「{removed}」ね。はいはい、アンタの記憶から消してあげたわよ。")
        else:
            await ctx.send('その番号の記憶なんて、元からないんだけど？')

    @commands.command()
    async def setname(self, ctx, *, new_name: str = None):
        if not new_name:
            await ctx.send('はぁ？ 新しい名前をちゃんと書きなさいよね！ 例：`!setname ご主人様`')
            return
        memory = load_memory()
        user_id = str(ctx.author.id)
        if user_id not in memory.get('users', {}):
            memory['users'][user_id] = {'notes': []}
        memory['users'][user_id]['fixed_nickname'] = new_name
        save_memory(memory)
        await ctx.send(f"ふん、アンタのこと、これからは「{new_name}」って呼んでやんよ♡ ありがたく思いなさいよね！")

    @commands.command()
    async def myname(self, ctx):
        memory = load_memory()
        user_id = str(ctx.author.id)
        nickname = memory.get('users', {}).get(user_id, {}).get('fixed_nickname')
        if nickname:
            await ctx.send(f"アンタの名前は「{nickname}」でしょ？ アタシがそう決めたんだから、文句ないわよね？♡")
        else:
            await ctx.send(f"アンタ、まだアタシに名前を教えてないじゃない。`!setname [呼ばれたい名前]` でアタシに教えなさいよね！")

    @commands.command()
    async def server_remember(self, ctx, *, note: str = None):
        if not note:
            await ctx.send("サーバーの共有知識として何を覚えさせたいわけ？ 内容を書きなさい！")
            return
        memory = load_memory()
        if 'server' not in memory: memory['server'] = {'notes': []}
        memory['server']['notes'].append(note)
        save_memory(memory)
        await ctx.send(f"ふーん、「{note}」ね。サーバーみんなのために覚えててやんよ♡")
        
    @commands.command()
    async def server_recall(self, ctx):
        memory = load_memory()
        if memory.get('server') and memory['server'].get('notes'):
            notes = "\n".join([f"- {note}" for note in memory['server']['notes']])
            await ctx.send(f"サーバーの共有知識リストよ！\n{notes}")
        else:
            await ctx.send("サーバーの共有知識はまだ何もないわよ？")

async def setup(bot):
    await bot.add_cog(UserCommands(bot))