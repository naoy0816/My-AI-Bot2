# cogs/commands.py (修正後)
# ... (冒頭部分は変更なし) ...
class UserCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
        # ▼▼▼ モデルの定義方法を修正 ▼▼▼
        self.model = genai.GenerativeModel('gemini-1.5-flash')

    # ... (google_search, todo はそのまま) ...

    # ▼▼▼ search コマンドのAI呼び出しを修正 ▼▼▼
    @commands.command(aliases=['g', 'google'])
    async def search(self, ctx, *, query: str = None):
        # ...
        async with ctx.typing():
            # ...
            try:
                # ▼▼▼ AIモデルの呼び出し方を修正 ▼▼▼
                response = await self.model.generate_content_async(synthesis_prompt)
                await ctx.send(response.text)
            except Exception as e:
                await ctx.send(f"エラーが発生しました: {e}")

    # ▼▼▼ testnews コマンドのAI呼び出しを修正 ▼▼▼
    @commands.command()
    async def testnews(self, ctx):
        # ...
        async with ctx.typing():
            # ...
            try:
                # ▼▼▼ AIモデルの呼び出し方を修正 ▼▼▼
                response = await self.model.generate_content_async(synthesis_prompt)
                await ctx.send(response.text)
            except Exception as e:
                await ctx.send(f"エラーが発生しました: {e}")

    # ... (以降の記憶コマンド remember, recall, forget, setname, myname, server_remember, server_recall は変更なし) ...
    # (ただし、ai_chat.pyの_get_embedding関数を呼び出す形になっていることを確認)

async def setup(bot):
    await bot.add_cog(UserCommands(bot))
