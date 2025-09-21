import discord
from discord.ext import commands, tasks
import os
import requests
import datetime
import json
import google.generativeai as genai

# --- APIキーとチャンネルIDは、環境変数から読み込む ---
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')
NEWS_API_KEY = os.getenv('NEWS_API_KEY')
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
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
        # ▼▼▼ 実行したい時間をここで設定するのよ！ （例は朝8時00分）▼▼▼
        target_time = datetime.time(hour=8, minute=0, tzinfo=jst)
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
            await channel.send(f"おはよ、ザコども♡ 今 {datetime.datetime.now(jst).hour}時よ。アタシが今日の情報を授けてあげる！")
            
            # --- 天気予報 ---
            weather_report = self.get_weather()
            await channel.send(weather_report)
            
            # --- ニュース ---
            news_report = self.get_news()
            await channel.send(news_report)
            
            # --- 記憶の整理 ---
            await self.consolidate_memory()
            print("アタシの記憶、整理しといたわよ♡")

    # 天気予報を取得する関数
    def get_weather(self):
        if not WEATHER_API_KEY: return "（天気APIキーが設定されてないわよ、ザコ♡）"
        city = "Tokoname" # 都市名は好きに変えなさい
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&lang=ja&units=metric"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            description = data['weather'][0]['description']
            temp = data['main']['temp']
            return f"今日の**{city}**の天気は「{description}」、気温は{temp}℃よ。アンタ、傘とか服装とか、ちゃんと考えなさいよね！"
        except Exception as e:
            print(f"Weather API error: {e}")
            return "天気の取得に失敗したわ。アンタの日頃の行いが悪いんじゃない？w"

    # ニュースを取得する関数
    def get_news(self):
        if not NEWS_API_KEY: return "（ニュースAPIキーが設定されてないわよ、ザコ♡）"
        url = f"https://newsapi.org/v2/top-headlines?country=jp&apiKey={NEWS_API_KEY}"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            headlines = [f"・ {article['title']}" for article in data['articles'][:3]]
            return "アタシが今日のトップニュースを3つだけ教えてあげる♡\n" + "\n".join(headlines)
        except Exception as e:
            print(f"News API error: {e}")
            return "ニュースの取得に失敗したわ。世の中はアンタが思ってるより複雑なのよ。たぶんね。"

    # 記憶を整理する関数
    async def consolidate_memory(self):
        print("Starting memory consolidation...")
        memory = load_memory()
        
        # ここでは簡単な例として、サーバーノートの重複を削除するだけにするわ
        # もっと賢くするには、AIに要約させたりする必要があるわね
        if 'server' in memory and 'notes' in memory['server']:
            original_count = len(memory['server']['notes'])
            unique_notes = list(dict.fromkeys(memory['server']['notes']))
            memory['server']['notes'] = unique_notes
            new_count = len(unique_notes)
            
            if original_count > new_count:
                save_memory(memory)
                print(f"Consolidated server memory. Removed {original_count - new_count} duplicate notes.")
        
        # ログとしてチャンネルに通知
        channel = self.bot.get_channel(NOTICE_CHANNEL_ID)
        if channel:
            await channel.send("（ふん、アタシの脳内（記憶）も整理整頓して、もっと賢くなっといたわよ♡）")

async def setup(bot):
    await bot.add_cog(DailyTasks(bot))
