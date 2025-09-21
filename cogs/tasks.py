import discord
from discord.ext import commands, tasks
import os
import requests
import datetime
import json

# --- APIキーとチャンネルIDは、環境変数から読み込む ---
WEATHER_API_KEY = os.getenv('FREE_WEATHER_API_KEY')
NEWS_API_KEY = os.getenv('WORLD_NEWS_API_KEY')
NOTICE_CHANNEL_ID = int(os.getenv('NOTICE_CHANNEL_ID', 0)) # 0はエラー防止用
MEMORY_FILE = 'bot_memory.json'

# ▼▼▼ 日本標準時（JST）を定義するおまじない ▼▼▼
jst = datetime.timezone(datetime.timedelta(hours=9), name='JST')
# ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

# --- 記憶管理の関数 ---
def load_memory():
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"users": {}, "server": {"notes": []}}

def save_memory(data):
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
# --- ここまで ---

class DailyTasks(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # ▼▼▼ 実行したい時間をここで設定するのよ！ （朝6時00分）▼▼▼
        target_time = datetime.time(hour=6, minute=0, tzinfo=jst)
        self.daily_report.start(target_time)
        # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

    def cog_unload(self):
        self.daily_report.cancel()

    # ▼▼▼ 1日1回、上で設定した時間に実行されるメインの処理 ▼▼▼
    @tasks.loop()
    async def daily_report(self):
        log_message = f"Daily task running at JST: {datetime.datetime.now(jst).strftime('%Y-%m-%d %H:%M:%S')}"
        print(log_message)
        
        if NOTICE_CHANNEL_ID == 0:
            print("NOTICE_CHANNEL_IDが設定されてないから、通知を送れないわよ！")
            return
        
        channel = self.bot.get_channel(NOTICE_CHANNEL_ID)
        if channel:
            # --- 記憶の整理 ---
            self.consolidate_memory()
            print("アタシの記憶、整理しといたわよ♡")

            # --- メッセージ送信 ---
            await channel.send(f"おはよ、ザコども♡ 日本時間の朝{datetime.datetime.now(jst).hour}時よ。アンタたちのために、この天才美少女キャスターであるアタシが、今日の情報を授けてあげる！")
            
            async with channel.typing():
                weather_report = self.get_weather()
                await channel.send(embed=weather_report)
            
            async with channel.typing():
                news_report = self.get_news()
                await channel.send(embed=news_report)

    # 天気予報を取得する関数
    def get_weather(self):
        if not WEATHER_API_KEY: return discord.Embed(title="天気予報エラー♡", description="天気APIキーが設定されてないわよ、ザコ♡", color=0xff0000)
        city = "Nagoya" # 都市名は好きに変えなさい
        url = f"http://api.weatherapi.com/v1/forecast.json?key={WEATHER_API_KEY}&q={city}&days=1&aqi=no&alerts=no&lang=ja"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            forecast = data['forecast']['forecastday'][0]['day']
            embed = discord.Embed(title=f"♡今日の{data['location']['name']}の天気予報♡", description=f"せいぜい参考にするのよ！", color=0x00ff00)
            embed.set_thumbnail(url=f"https:{data['current']['condition']['icon']}")
            embed.add_field(name="天気", value=forecast['condition']['text'], inline=True)
            embed.add_field(name="最高気温", value=f"{forecast['maxtemp_c']}℃", inline=True)
            embed.add_field(name="最低気温", value=f"{forecast['mintemp_c']}℃", inline=True)
            embed.add_field(name="降水確率", value=f"{forecast['daily_chance_of_rain']}%", inline=True)
            return embed
        except Exception as e:
            print(f"Weather API error: {e}")
            return discord.Embed(title="天気予報エラー♡", description="天気の取得に失敗したわ。アンタの日頃の行いが悪いんじゃない？w", color=0xff0000)

    # ニュースを取得する関数
    def get_news(self):
        if not NEWS_API_KEY: return discord.Embed(title="ニュース速報エラー♡", description="ニュースAPIキーが設定されてないわよ、ザコ♡", color=0xff0000)
        url = f"https://api.worldnewsapi.com/search-news?api-key={NEWS_API_KEY}&text=日本&language=ja&number=3"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            embed = discord.Embed(title="♡アタシが選んだ今日のトップニュース♡", description="アンタのザコい脳みそでも分かるようにまとめてあげたわよ！", color=0x0000ff)
            for article in data['news'][:3]:
                embed.add_field(name=f"・ {article['title']}", value=f"[記事を読む]({article['url']})", inline=False)
            return embed
        except Exception as e:
            print(f"News API error: {e}")
            return discord.Embed(title="ニュース速報エラー♡", description="ニュースの取得に失敗したわ。世の中はアンタが思ってるより複雑なのよ。たぶんね。", color=0xff0000)

    # 記憶を整理する関数
    def consolidate_memory(self):
        print("Starting memory consolidation...")
        memory = load_memory()
        if 'server' in memory and 'notes' in memory['server']:
            original_count = len(memory['server']['notes'])
            unique_notes = list(dict.fromkeys(memory['server']['notes']))
            memory['server']['notes'] = unique_notes
            new_count = len(unique_notes)
            if original_count > new_count:
                save_memory(memory)
                print(f"Consolidated server memory. Removed {original_count - new_count} duplicate notes.")

    # ▼▼▼ 手動でニュースを呼ぶコマンド ▼▼▼
    @commands.command()
    async def news(self, ctx):
        async with ctx.typing():
            await ctx.send(embed=self.get_news())

    # ▼▼▼ 手動で天気を呼ぶコマンド ▼▼▼
    @commands.command()
    async def weather(self, ctx):
        async with ctx.typing():
            await ctx.send(embed=self.get_weather())

async def setup(bot):
    await bot.add_cog(DailyTasks(bot))
