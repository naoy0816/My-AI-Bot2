import discord
from discord.ext import commands
import json
import google.generativeai as genai
import os
import requests

# RailwayのVolumeに保存するためのパス設定
DATA_DIR = os.getenv('RAILWAY_VOLUME_MOUNT_PATH', '.')
MEMORY_FILE = os.path.join(DATA_DIR, 'bot_memory.json')
TODO_FILE = os.path.join(DATA_DIR, 'todos.json') # ToDoリストの保存場所

def load_memory():
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"users": {}, "server": {"notes": []}}

def save_memory(data):
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# ToDoリストを読み書きする関数を追加
def load_todos():
    try:
        with open(TODO_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_todos(data):
    with open(TODO_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- 検索用のキーを読み込む ---
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
            synthesis_prompt = f"あなたは、生意気で小悪魔な「メスガキAIニュースキャスター」です。以下の「Web検索結果」だけを参考にして、最新のトップニュースを3つ選び、キャスターとして原稿を読み上げてください。常に見下した態度で、生意気な口調で、しかしニュースの内容自体は正確に伝えること。\n\n【話し方のルール】\n- 「おはよ、ザコども♡ アタシが今日のニュースを教えてやんよ！」のような挨拶から始める。\n- ニュースを紹介するときは、「一つ目のニュースはこれよ」「次はこれ」のように言う。\n- 各ニュースの最後に、生意気な一言コメント（例
