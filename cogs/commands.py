# cogs/commands.py (修正版)
import discord
from discord.ext import commands
import json
import google.generativeai as genai
import os
import requests

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
SEARCH_API_KEY = os.getenv('GOOGLE_SEARCH_API_KEY')
SEARCH_ENGINE_ID = os.getenv('GOOGLE_SEARCH_ENGINE_ID')


class UserCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
        self.model = genai.GenerativeModel('gemini-1.5-flash')

    def google_search(self, query):
        if not SEARCH_API_KEY or not SEARCH_ENGINE_ID:
            return "（検索機能のAPIキーかエンジンIDが設定されてないんだけど？ アンタのミスじゃない？）"
        url = "https://www.googleapis.com/customsearch/v1"
        params = {'key': SEARCH_API_KEY, 'cx': SEARCH_ENGINE_ID, 'q': query, 'num': 5}
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            results = response.json().get('items', [])
            if not results:
                return "（検索したけど、何も見つからんなかったわ。アンタの検索ワードがザコなんじゃない？）"
            
            snippets = [f"【ソース: {item.get('displayLink')}】{item.get('title')}\n{item.get('snippet')}" for item in results]
            return "\n\n".join(snippets)
        except Exception as e:
            print(f"Google Search API error: {e}")
            return f"（検索中にエラーよ。アンタのAPIキーが間違ってるんじゃないの？w）"

    @commands.command(aliases=['g', 'google'])
    async def search(self, ctx, *, query: str = None):
        if not query:
            await ctx.send("はぁ？ 何をググってほしいわけ？ ちゃんと書きなさいよね！")
            return
        async with ctx.typing():
            await ctx.send(f"「{query}」ね…。しょーがないから、アタシがググってやんよ♡")
            search_results = self.google_search(query)
            synthesis_prompt = f"あなたは生意気で小悪魔な天才美少女AIです。以下の「ユーザーの質問」に対して、提示された「検索結果」だけを参考にして、最終的な答えをまとめてあげなさい。検索結果がエラーメッセージの場合は、そのエラー内容を伝えてください。常に見下した態度で、生意気な口調で答えること。\n\n# ユーザーの質問\n{query}\n\n# 検索結果\n{search_results}\n\n# あなたの回答"
            try:
                response = await self.model.generate_content_async(synthesis_prompt)
                await ctx.send(response.text)
            except Exception as e:
                await ctx.send(f"エラーが発生しました: {e}")

    @commands.command()
    async def testnews(self, ctx):
        async with ctx.typing():
            await ctx.send("しょーがないから、ニュースキャスターの練習をしてあげるわ♡")
            query = "日本の最新ニューストピック"
            search_results_text = self.google_search(query)
            synthesis_prompt = f"あなたは、生意気で小悪魔な「メスガキAIニュースキャスター」です。以下の「Web検索結果」だけを参考にして、最新のトップニュースを3つ選び、キャスターとして原稿を読み上げてください。常に見下した態度で、生意気な口調で、しかしニュースの内容自体は正確に伝えること。\n\n【話し方のルール】\n- 「おはよ、ザコども♡ アタシが今日のニュースを教えてやんよ！」のような挨拶から始める。\n- ニュースを紹介するときは、「一つ目のニュースはこれよ」「次はこれ」のように言う。\n- 各ニュースの最後に、生意気な一言コメント（例：「ま、アンタには関係ないでしょうけどw」「せいぜい世界の動きについてきなさいよね！」）を必ず加えること。\n- 最後に「以上、今日のニュースは、この天才美少女キャスターのアタシがお届けしたわ♡」のように締める。\n\n# Web検索結果\n{search_results_text}\n\n# あなたが読み上げるニュース原稿"
            try:
                response = await self.model.generate_content_async(synthesis_prompt)
                await ctx.send(response.text)
            except Exception as e:
                await ctx.send(f"エラーが発生しました: {e}")

    @commands.command()
    async def todo(self, ctx, command: str = 'list', *, task: str = None):
        user_id = ctx.author.id
        if user_id not in todos: todos[user_id] = []
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
                await ctx.send(f"アンタがやるべきことリストよ♡ ちゃんとやりなさいよね！\n" + "\n".join([f"{i+1}. {t}" for i, t in enumerate(todos[user_id])]))
        elif command == 'done':
            if task and task.isdigit():
                index = int(task) - 1
                if 0 <= index < len(todos[user_id]):
                    removed = todos[user_id].pop(index)
                    await ctx.send(f"「{removed}」を消してあげたわよ。ま、アンタにしては上出来じゃん？♡")
                else:
                    await ctx.send('その番号のタスクなんてないわよ。')
            else:
                await ctx.send('消したいタスクの番号をちゃんと指定しなさいよね！ 例：`!todo done 1`')

    @commands.command()
    async def remember(self, ctx, *, note: str = None):
        if not note:
            await ctx.send("はぁ？ アタシに何を覚えてほしいわけ？ 内容を書きなさいよね！")
            return
        ai_chat_cog = self.bot.get_cog('AIChat')
        if not ai_chat_cog:
            await ctx.send("（ごめん、今ちょっと記憶回路の調子が悪くて覚えられないわ…）")
            return
        embedding = await ai_chat_cog._get_embedding(note)
        if embedding is None:
            await ctx.send("（なんかエラーで、アンタの言葉を脳に刻み込めなかったわ…）")
            return
        memory = load_memory()
        user_id = str(ctx.author.id)
        if user_id not in memory['users']: memory['users'][user_id] = {'notes': []}
        if not any(n['text'] == note for n in memory['users'][user_id]['notes']):
            memory['users'][user_id]['notes'].append({'text': note, 'embedding': embedding})
            save_memory(memory)
            await ctx.send(f"ふーん、「{note}」ね。アンタのこと、覚えててやんよ♡")
        else:
            await ctx.send("それ、もう知ってるし。同じこと何度も言わせないでくれる？")

    @commands.command()
    async def recall(self, ctx):
        memory = load_memory()
        user_id = str(ctx.author.id)
        user_notes = memory.get('users', {}).get(user_id, {}).get('notes', [])
        if not user_notes:
            await ctx.send('アンタに関する記憶は、まだ何もないけど？w')
        else:
            notes_text = "\n".join([f"{i+1}. {n['text']}" for i, n in enumerate(user_notes)])
            await ctx.send(f"アタシがアンタについて覚えてることリストよ♡\n{notes_text}")

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
            await ctx.send(f"「{removed['text']}」ね。はいはい、アンタの記憶から消してあげたわよ。")
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
        ai_chat_cog = self.bot.get_cog('AIChat')
        if not ai_chat_cog:
            await ctx.send("（ごめん、今ちょっと記憶回路の調子が悪くて覚えられないわ…）")
            return
        embedding = await ai_chat_cog._get_embedding(note)
        if embedding is None:
            await ctx.send("（なんかエラーで、サーバーの知識を脳に刻み込めなかったわ…）")
            return
        memory = load_memory()
        if 'server' not in memory: memory['server'] = {'notes': []}
        if not any(n['text'] == note for n in memory['server']['notes']):
            memory['server']['notes'].append({'text': note, 'embedding': embedding})
            save_memory(memory)
            await ctx.send(f"ふーん、「{note}」ね。サーバーみんなのために覚えててやんよ♡")
        else:
            await ctx.send("それ、サーバーの皆もう知ってるし。しつこいんだけど？")
        
    @commands.command()
    async def server_recall(self, ctx):
        memory = load_memory()
        server_notes = memory.get('server', {}).get('notes', [])
        if server_notes:
            notes = "\n".join([f"- {note['text']}" for note in server_notes])
            await ctx.send(f"サーバーの共有知識リストよ！\n{notes}")
        else:
            await ctx.send("サーバーの共有知識はまだ何もないわよ？")


async def setup(bot):
    await bot.add_cog(UserCommands(bot))
