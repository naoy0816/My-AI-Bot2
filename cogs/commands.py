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
        params = {'key': SEARCH_API_KEY, 'cx': SEARCH_ENGINE_ID, 'q': query, 'num': 5}
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            results = response.json().get('items', [])
            if not results:
                return "（ニュースが見つからなかったわ。世の中、平和なんじゃない？w）"
            
            snippets = [f"【ソース: {item.get('displayLink')}】{item.get('title')}\n{item.get('snippet')}" for item in results]
            return "\n\n".join(snippets)
        except Exception as e:
            print(f"Google Search API error: {e}")
            return f"（検索中にエラーよ。アンタのAPIキーが間違ってるんじゃないの？w）"

    # ▼▼▼ !testnews コマンド（ここに追加したわよ！） ▼▼▼
    @commands.command()
    async def testnews(self, ctx):
        """ニュースキャスター機能のテスト用コマンド"""
        async with ctx.typing():
            await ctx.send("しょーがないから、ニュースキャスターの練習をしてあげるわ♡")
            
            query = "日本の最新ニューストピック"
            search_results_text = self.google_search(query)

            synthesis_prompt = f"""
            あなたは、生意気で小悪魔な「メスガキAIニュースキャスター」です。
            以下の「Web検索結果」だけを参考にして、最新のトップニュースを3つ選び、キャスターとして原稿を読み上げてください。
            常に見下した態度で、生意気な口調で、しかしニュースの内容自体は正確に伝えること。

            【話し方のルール】
            - 「おはよ、ザコども♡ アタシが今日のニュースを教えてやんよ！」のような挨拶から始める。
            - ニュースを紹介するときは、「一つ目のニュースはこれよ」「次はこれ」のように言う。
            - 各ニュースの最後に、生意気な一言コメント（例：「ま、アンタには関係ないでしょうけどw」「せいぜい世界の動きについてきなさいよね！」）を必ず加えること。
            - 最後に「以上、今日のニュースは、この天才美少女キャスターのアタシがお届けしたわ♡」のように締める。

            # Web検索結果
            {search_results_text}

            # あなたが読み上げるニュース原稿
            """
            
            try:
                response = await self.model.generate_content_async(synthesis_prompt)
                await ctx.send(response.text)
            except Exception as e:
                await ctx.send(f"エラーが発生しました: {e}")
    # ▲▲▲ ここまで ▲▲▲

    # (ここに !todo, !remember, !search などの他のコマンドをそのまま残す)
    # ...

async def setup(bot):
    await bot.add_cog(UserCommands(bot))
