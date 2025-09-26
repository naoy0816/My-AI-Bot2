# cogs/tasks.py (修正版)
import discord
from discord.ext import commands, tasks
import os
import requests
import datetime
import json
import google.generativeai as genai
from . import _utils as utils

DATA_DIR = os.getenv('RAILWAY_VOLUME_MOUNT_PATH', '.')
MEMORY_FILE = os.path.join(DATA_DIR, 'bot_memory.json')

NOTICE_CHANNEL_ID = int(os.getenv('NOTICE_CHANNEL_ID', 0))
WEATHER_LATITUDE = float(os.getenv('WEATHER_LATITUDE', 35.1815))
WEATHER_LONGITUDE = float(os.getenv('WEATHER_LONGITUDE', 136.9066))

jst = datetime.timezone(datetime.timedelta(hours=9), name='JST')
TARGET_TIME = datetime.time(hour=6, minute=0, tzinfo=jst)

class DailyTasks(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
        self.model = genai.GenerativeModel('gemini-1.5-flash-latest') # ★★★ モデル名を修正 ★★★
        self.daily_report.start()

    def cog_unload(self):
        self.daily_report.cancel()

    def weather_code_to_emoji(self, code):
        if code == 0: return "快晴☀️"
        if code == 1: return "晴れ☀️"
        if code == 2: return "一部曇り🌤️"
        if code == 3: return "曇り☁️"
        if 45 <= code <= 48: return "霧🌫️"
        if 51 <= code <= 55: return "霧雨🌦️"
        if 61 <= code <= 65: return "雨☔"
        if 71 <= code <= 75: return "雪❄️"
        if 80 <= code <= 82: return "にわか雨🌧️"
        if 95 <= code <= 99: return "雷雨⛈️"
        return "よくわかんない天気"

    def get_weather_open_meteo(self):
        lat, lon = WEATHER_LATITUDE, WEATHER_LONGITUDE
        url = f"https://api.open-meteo.com/v1/jma?latitude={lat}&longitude={lon}&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=Asia%2FTokyo"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()['daily']
            embed = discord.Embed(title="♡今日の天気予報♡", description="せいぜい参考にするのよ！", color=0x00ff00)
            embed.add_field(name="天気", value=self.weather_code_to_emoji(data['weather_code'][0]), inline=True)
            embed.add_field(name="最高気温", value=f"{data['temperature_2m_max'][0]}℃", inline=True)
            embed.add_field(name="最低気温", value=f"{data['temperature_2m_min'][0]}℃", inline=True)
            embed.add_field(name="降水確率", value=f"{data['precipitation_probability_max'][0]}%", inline=True)
            return embed
        except Exception as e:
            print(f"Open-Meteo API error: {e}")
            return discord.Embed(title="天気予報エラー♡", description="天気の取得に失敗したわ。アンタの日頃の行いが悪いんじゃない？w", color=0xff0000)

    @tasks.loop(time=TARGET_TIME)
    async def daily_report(self):
        if NOTICE_CHANNEL_ID == 0:
            print("NOTICE_CHANNEL_IDが設定されてないから、通知を送れないわよ！")
            return
        
        channel = self.bot.get_channel(NOTICE_CHANNEL_ID)
        if not channel:
            print(f"チャンネルID({NOTICE_CHANNEL_ID})が見つからないんだけど？")
            return
            
        await channel.send(f"おはよ、ザコども♡ 日本時間の朝{datetime.datetime.now(jst).hour}時よ。アンタたちのために、この天才美少女キャスターであるアタシが、今日の情報を授けてあげる！")
        
        async with channel.typing():
            weather_report = self.get_weather_open_meteo()
            await channel.send(embed=weather_report)
        
        await asyncio.sleep(2)

        async with channel.typing():
            query = "日本の最新ニューストピック"
            search_results = utils.google_search(query)
            
            if isinstance(search_results, str):
                await channel.send(search_results); return
            if not search_results:
                await channel.send("（ニュースが見つからなかったわ。世の中、平和なんじゃない？w）"); return

            search_results_text = "\n\n".join([f"【ソース: {item.get('displayLink')}】{item.get('title')}\n{item.get('snippet')}" for item in search_results])

            synthesis_prompt = f"あなたは、生意気で小悪魔な「メスガキAIニュースキャスター」です。以下の「Web検索結果」だけを参考にして、最新のトップニュースを3つ選び、キャスターとして原稿を読み上げてください。常に見下した態度で、生意気な口調で、しかしニュースの内容自体は正確に伝えること。\n\n【話し方のルール】\n- ニュースを紹介するときは、「一つ目のニュースはこれよ」「次はこれ」のように言う。\n- 各ニュースの最後に、生意気な一言コメント（例：「ま、アンタには関係ないでしょうけどw」「せいぜい世界の動きについてきなさいよね！」）を必ず加えること。\n- 最後に「以上、今日のニュースは、この天才美少女キャスターのアタシがお届けしたわ♡」のように締める。\n\n# Web検索結果\n{search_results_text}\n\n# あなたが読み上げるニュース原稿"
            try:
                response = await self.model.generate_content_async(synthesis_prompt)
                await channel.send(response.text)
            except Exception as e:
                print(f"News synthesis error: {e}")
                await channel.send("（ごめん、ニュース原稿を作ろうとしたらエラーが出たわ…AIの機嫌が悪いんじゃない？）")

async def setup(bot):
    await bot.add_cog(DailyTasks(bot))
