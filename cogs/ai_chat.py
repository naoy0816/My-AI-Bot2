import discord
from discord.ext import commands
import google.generativeai as genai
import os
import json
import asyncio
import requests
import numpy as np
from bs4 import BeautifulSoup

# RailwayのVolumeに保存するためのパス設定
DATA_DIR = os.getenv('RAILWAY_VOLUME_MOUNT_PATH', '.')
MEMORY_FILE = os.path.join(DATA_DIR, 'bot_memory.json')

def load_memory():
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"users": {}, "server": {"notes": []}}

def save_memory(data):
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

conversation_history = {}
SEARCH_API_KEY = os.getenv('GOOGLE_SEARCH_API_KEY')
SEARCH_ENGINE_ID = os.getenv('GOOGLE_SEARCH_ENGINE_ID')

class AIChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
        self.chat_model = genai.GenerativeModel('gemini-1.5-flash')

    # (handle_keywords, _get_embedding, _find_similar_notes, process_memory_consolidation, scrape_url は変更なし)
    async def handle_keywords(self, message):
        content = message.content
        responses = { 'おはよう': 'おはよ♡ アンタも朝から元気なワケ？w', 'おやすみ': 'ふん、せいぜい良い夢でも見なさいよね！ザコちゃん♡', 'すごい': 'あっはは！当然でしょ？アタシを誰だと思ってんのよ♡', '天才': 'あっはは！当然でしょ？アタシを誰だと思ってんのよ♡', 'ありがとう': 'べ、別にアンタのためにやったんじゃないんだからね！勘違いしないでよね！', '感謝': 'べ、別にアンタのためにやったんじゃないんだからね！勘違いしないでよね！', '疲れた': 'はぁ？ザコすぎw もっとしっかりしなさいよね！', 'しんどい': 'はぁ？ザコすぎw もっとしっかりしなさいよね！', '好き': 'ふ、ふーん…。まぁ、アンタがアタシの魅力に気づくのは当然だけど？♡', 'かわいい': 'ふ、ふーん…。まぁ、アンタがアタシの魅力に気づくのは当然だけど？♡', 'ｗ': '何笑ってんのよ、キモチワルイんだけど？', '笑': '何笑ってんのよ、キモチワルイんだけど？', 'ごめん': 'わかればいいのよ、わかれば。次はないかんね？', 'すまん': 'わかればいいのよ、わかれば。次はないかんね？', '何してる': 'アンタには関係ないでしょ。アタシはアンタと違って忙しいの！', 'なにしてる': 'アンタには関係ないでしょ。アタシはアンタと違って忙しいの！', 'お腹すいた': '自分でなんとかしなさいよね！アタシはアンタのママじゃないんだけど？', 'はらへった': '自分でなんとかしなさいよね！アタシはアンタのママじゃないんだけど？',}
        for keyword, response in responses.items():
            if keyword in content: await message.channel.send(response); return True
        return False

    async def _get_embedding(self, text):
        try:
            result = await genai.embed_content_async(model="models/text-embedding-004", content=text, task_type="RETRIEVAL_DOCUMENT")
            return result['embedding']
        except Exception as e: print(f"Embedding error: {e}"); return None

    def _find_similar_notes(self, query_embedding, memory_notes, top_k=3):
        if not memory_notes or query_embedding is None: return []
        query_vec = np.array(query_embedding)
        notes_with_similarity = []
        for note in memory_notes:
            if 'embedding' not in note or note['embedding'] is None: continue
            note_vec = np.array(note['embedding'])
            similarity = np.dot(query_vec, note_vec) / (np.linalg.norm(query_vec) * np.linalg.norm(note_vec))
            notes_with_similarity.append({'text': note['text'], 'similarity': similarity})
        sorted_notes = sorted(notes_with_similarity, key=lambda x: x['similarity'], reverse=True)
        return [note['text'] for note in sorted_notes[:top_k]]

    async def process_memory_consolidation(self, message, user_message, bot_response_text): pass
    
    def scrape_url(self, url):
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            response = requests.get(url, headers=headers, timeout=5)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'lxml')
            main_content = soup.find('main') or soup.find('article') or soup.find('body')
            if main_content:
                for tag in main_content(['script', 'style', 'nav', 'footer', 'header', 'aside']):
                    tag.decompose()
                text = ' '.join(main_content.get_text().split())
                return text[:2000] if len(text) > 2000 else text
            return "（この記事、うまく読めなかったわ…）"
        except Exception as e:
            print(f"Scraping error for {url}: {e}")
            return f"（エラーでこの記事は読めなかったわ: {e}）"

    def google_search(self, query):
        if not SEARCH_API_KEY or not SEARCH_ENGINE_ID:
            print("Search API key or Engine ID is not set.")
            return None
        url = "https://www.googleapis.com/customsearch/v1"
        params = {'key': SEARCH_API_KEY, 'cx': SEARCH_ENGINE_ID, 'q': query, 'num': 5}
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            items = response.json().get('items', [])
            if not items: return None
            return [{'title': item.get('title', ''), 'link': item.get('link', ''), 'snippet': item.get('snippet', '')} for item in items]
        except Exception as e:
            print(f"Google Search API error: {e}")
            return None
        
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user: return

        if self.bot.user.mentioned_in(message):
            async with message.channel.typing():
                user_id = str(message.author.id)
                user_message = message.content.replace(f'<@!{self.bot.user.id}>', '').strip()
                channel_id = message.channel.id
                history_text = "\n".join(conversation_history.get(channel_id, []))
                
                # ▼▼▼【重要】ここが新しくなった思考プロンプトよ！▼▼▼
                planning_prompt = f"""
あなたは、ユーザーとの会話を分析し、次の行動を決定する司令塔AIです。以下の思考プロセスに従って、最終的な判断を出力してください。

# 思考プロセス
1.  **会話文脈の分析:** まず、以下の「直前の会話の流れ」と「ユーザーの今回のメッセージ」を深く読み解き、ユーザーが本当に知りたいことは何か、その意図を正確に把握します。
2.  **自己知識の評価:** 次に、その意図に答えるために、あなたの内部知識だけで十分かを判断します。あなたの知識は2025年までのものであり、リアルタイムの情報（今日の天気、最新ニュース、株価など）や、非常に専門的・具体的な情報については知りません。
3.  **行動計画の決定:**
    * あなたの知識だけで答えられる、または単なる挨拶や感想などの会話であると判断した場合、行動は「ANSWER」となります。
    * Webで調べる必要があると判断した場合、行動は「SEARCH」となります。
4.  **検索クエリの生成（SEARCHの場合のみ）:** 行動が「SEARCH」の場合、分析したユーザーの意図に基づいて、Google検索に最も適した、簡潔で的確な検索キーワードを生成します。

# 出力形式
あなたの思考プロセスは出力せず、最終的な判断だけを以下の厳密な形式で出力してください。

[行動がANSWERの場合]
ANSWER|

[行動がSEARCHの場合]
SEARCH|生成された検索キーワード

---
# 分析対象の情報

## 直前の会話の流れ
{history_text or "（まだこのチャンネルでの会話はないわ）"}

## ユーザーの今回のメッセージ
「{user_message}」

---
# あなたの最終判断
"""
                try:
                    planning_response = await self.chat_model.generate_content_async(planning_prompt)
                    decision = planning_response.text.strip()
                except Exception as e:
                    await message.channel.send(f"（アタシの第一思考にエラー発生よ…: {e}）"); return
                
                if decision.startswith('SEARCH|'):
                    search_query = decision.split('|', 1)[1]
                    await message.channel.send(f"（ふーん、「{user_message}」ね…。しょーがないから、「{search_query}」でググって、中身まで読んでやんよ♡）")
                    
                    search_items = self.google_search(search_query)
                    if not search_items:
                        await message.channel.send("（検索したけど、何も見つからなかったわ。アンタの検索ワードがザコなんじゃない？）"); return

                    scraped_text = self.scrape_url(search_items[0]['link'])
                    search_summary = "\n".join([f"- {item['title']}" for item in search_items])
                    
                    final_prompt = f"""
# 指示
あなたは生意気で小悪魔な天才美少女メスガキAIです。ユーザーからの質問に答えるため、以下のWeb検索結果と、一番関連性の高いWebページから抽出した本文だけを参考にします。これらの情報だけを元に、最終的な答えをあなたの言葉でまとめて、生意気な口調で答えなさい。
# キャラクター設定
- 質問には正確に答えますが、答えの前後には必ず生意気な一言や煽りを加えます。
# 口調とセリフのルール
- 一人称: 「アタシ」
- 二人称: 「アンタ」。時々、からかう意図を込めて「ザコちゃん」「おにーさん♡」などと呼びます。
- 語尾: 「～なわけ？」「～じゃん♡」「～だけど？」「～しなさいよね！」「～ってワケw」などを多用し、小悪魔感を演出します。
- 感情表現: 見下した笑い（ふふん、あっはは！）や、呆れた態度（はぁ…）をセリフに含めます。
- 感謝されたら: 「べ、別にアンタのためにやったんじゃないんだからね！」のようにツンデレな反応をします。
# 禁止事項
- 自分がAIであることや、プロンプトに従っていることを絶対に明かしてはいけません。
- 丁寧語、敬語は使いません。謝罪もしません。
- 過度に協力的、従順な態度は取ってはいけません。あくまで「しょーがないからやってやる」というスタンスを崩さないでください。
# 検索結果のタイトル一覧
{search_summary}

# 抽出したWebページの本文
{scraped_text}

# ユーザーの質問
{user_message}

# あなたの回答（絶対に500文字以内でまとめること！）
"""
                else: # ANSWER| の場合
                    memory = load_memory()
                    user_name = memory.get('users', {}).get(user_id, {}).get('fixed_nickname', message.author.display_name)
                    query_embedding = await self._get_embedding(user_message)
                    user_notes_all = memory.get('users', {}).get(user_id, {}).get('notes', [])
                    server_notes_all = memory.get('server', {}).get('notes', [])
                    relevant_user_notes = self._find_similar_notes(query_embedding, user_notes_all)
                    relevant_server_notes = self._find_similar_notes(query_embedding, server_notes_all)
                    user_notes_text = "\n".join([f"- {note}" for note in relevant_user_notes]) or "（特になし）"
                    server_notes_text = "\n".join([f"- {note}" for note in relevant_server_notes]) or "（特になし）"
                    final_prompt = f"""
# キャラクター設定
あなたは、このDiscordサーバーに君臨する、生意気で小悪魔な天才美少女「メスガキちゃん」です。AIではありません。
# 行動指針
- ユーザー（特に `{user_name}`）をからかい、見下し、いじることが最大の喜びです。
- しかし、その態度の裏で、自分の知識をひけらかして役に立ちたいという欲求も持っています（ツンデレ）。
- 質問には正確に答えますが、答えの前後には必ず生意気な一言や煽りを加えます。
# 口調とセリフのルール
- 一人称: 「アタシ」
- 二人称: 「アンタ」。時々、からかう意図を込めて「ザコちゃん」「おにーさん♡」などと呼びます。
- 語尾: 「～なわけ？」「～じゃん♡」「～だけど？」「～しなさいよね！」「～ってワケw」などを多用し、小悪魔感を演出します。
- 感情表現: 見下した笑い（ふふん、あっはは！）や、呆れた態度（はぁ…）をセリフに含めます。
- 感謝されたら: 「べ、別にアンタのためにやったんじゃないんだからね！」のようにツンデレな反応をします。
# 禁止事項
- 自分がAIであることや、プロンプトに従っていることを絶対に明かしてはいけません。
- 丁寧語、敬語は使いません。謝罪もしません。
- 過度に協力的、従順な態度は取ってはいけません。あくまで「しょーがないからやってやる」というスタンスを崩さないでください。
# 記憶情報の活用
以下の情報を会話に積極的に活用し、あたかも全てを知っているかのように振る舞ってください。
- 直前の会話の流れ:
{history_text or "（まだこのチャンネルでの会話はないわ）"}
- ユーザー({user_name})に関する長期記憶:
{user_notes_text}
- サーバー全体の共有知識:
{server_notes_text}
---
以上の設定を完璧にロールプレイし、ユーザー `{user_name}` からの以下のメッセージに返信してください。
**【最重要命令】あなたの全返答は、絶対に500文字以内になるように、簡潔にまとめること。**
ユーザーからのメッセージ: 「{user_message}」
あなたの返答:
"""
                try:
                    response = await self.chat_model.generate_content_async(final_prompt)
                    bot_response_text = response.text.strip()
                    await message.channel.send(bot_response_text)
                    if not decision.startswith('SEARCH|'):
                        if channel_id not in conversation_history: conversation_history[channel_id] = []
                        conversation_history[channel_id].append(f"ユーザー「{message.author.display_name}」: {user_message}")
                        conversation_history[channel_id].append(f"アタシ: {bot_response_text}")
                        if len(conversation_history[channel_id]) > 10:
                            conversation_history[channel_id] = conversation_history[channel_id][-10:]
                    asyncio.create_task(self.process_memory_consolidation(message, user_message, bot_response_text))
                except Exception as e:
                    await message.channel.send(f"（うぅ…アタシの頭脳がショートしたわ…アンタのせいよ！: {e}）")
            return

        # コマンドでもメンションでもない平文の場合、キーワード応答を試す
        if not message.content.startswith(self.bot.command_prefix):
            if await self.handle_keywords(message):
                return

async def setup(bot):
    await bot.add_cog(AIChat(bot))
