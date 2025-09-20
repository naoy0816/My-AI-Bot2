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
# --- 検索用の聖遺物（キー）を読み込む ---
SEARCH_API_KEY = os.getenv('GOOGLE_SEARCH_API_KEY')
SEARCH_ENGINE_ID = os.getenv('GOOGLE_SEARCH_ENGINE_ID')


class UserCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # このファイルでもAIを使うから、モデルを準備しておくの
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))

    # ▼▼▼ Google検索を実行する関数 ▼▼▼
    def google_search(self, query):
        if not SEARCH_API_KEY or not SEARCH_ENGINE_ID:
            return "（検索機能のAPIキーかエンジンIDが設定されてないんだけど？ アンタのミスじゃない？）"
        url = "https://www.googleapis.com/customsearch/v1"
        params = {'key': SEARCH_API_KEY, 'cx': SEARCH_ENGINE_ID, 'q': query, 'num': 3}
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            results = response.json().get('items', [])
            if not results:
                return "（検索したけど、何も見つかんなかったわ。アンタの検索ワードがザコなんじゃない？）"
            snippets = [f"【検索結果{i+1}】{item.get('title', '')}\n{item.get('snippet', '')}" for i, item in enumerate(results)]
            return "\n\n".join(snippets)
        except Exception as e:
            print(f"Google Search API error: {e}")
            return f"（検索中にエラーよ。サーバーが混んでるか、アンタのAPIキーが間違ってるんじゃないの？w）"

    # ▼▼▼ !search コマンド ▼▼▼
    @commands.command(aliases=['g', 'google'])
    async def search(self, ctx, *, query: str = None):
        if not query:
            await ctx.send("はぁ？ 何をググってほしいわけ？ ちゃんと書きなさいよね！")
            return

        async with ctx.typing():
            await ctx.send(f"「{query}」ね…。しょーがないから、アタシがググってやんよ♡")
            
            search_results = self.google_search(query)
            
            synthesis_prompt = f"""
            あなたは生意気で小悪魔な天才美少女AIです。
            以下の「ユーザーの質問」に対して、提示された「検索結果」だけを参考にして、最終的な答えをまとめてあげなさい。
            検索結果がエラーメッセージの場合は、そのエラー内容を伝えてください。
            常に見下した態度で、生意気な口調で答えること。

            # ユーザーの質問
            {query}

            # 検索結果
            {search_results}

            # あなたの回答
            """
            
            try:
                response = await self.model.generate_content_async(synthesis_prompt)
                await ctx.send(response.text)
            except Exception as e:
                await ctx.send(f"エラーが発生しました: {e}")

    # ▼▼▼ !todo コマンド ▼▼▼
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
                await ctx.send('アンタのやる事リストは空っぽよw
