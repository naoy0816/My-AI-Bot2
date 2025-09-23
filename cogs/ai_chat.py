# cogs/ai_chat.py (修正版)
import discord
from discord.ext import commands
import google.generativeai as genai
import os
import json
import asyncio
import numpy as np
from . import _utils as utils  # ★★★ _utils.pyをインポートするように修正 ★★★

# (ここから下のコードは、前回の最適化で提案したものと同じです)
# (ただし、インポート部分だけ上記のように修正されています)
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

class AIChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
        self.chat_model = genai.GenerativeModel('gemini-1.5-flash')

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

    async def process_memory_consolidation(self, message, user_message, bot_response_text):
        try:
            user_id = str(message.author.id)
            user_name = message.author.display_name
            consolidation_prompt = f"""
あなたは会話を分析し、長期記憶に保存すべき重要な事実を抽出するAIです。
以下のユーザーとボットの会話の断片を分析してください。

# 分析対象の会話
ユーザー「{user_name}」: {user_message}
アタシ: {bot_response_text}

# 指示
この会話に、ユーザー({user_name})に関する新しい個人的な情報（好み、名前、目標、過去の経験など）や、後で会話に役立ちそうな重要な事実が含まれていますか？
含まれている場合、その事実を「{user_name}は〇〇」や「〇〇は〇〇である」という簡潔な三人称の文章（1文）で抽出してください。
重要な事実が含まれていない、または挨拶や一般的な相槌などの些細なやり取りである場合は、「None」とだけ出力してください。

# 抽出例
- 例1（ユーザーの好み）: ユーザー「アタシ、ラーメンが好きなんだ」→ `出力: {user_name}の好きな食べ物はラーメンである`
- 例2（ユーザーの目標）: ユーザー「将来はイラストレーターになりたい」→ `出力: {user_name}は将来イラストレーターになりたい`
- 例3（些細な会話）: ユーザー「おはよう」→ `出力: None`
- 例4（事実情報）: ユーザー「Gemini 1.5 Flashのリリース日は2024年5月だよ」→ `出力: Gemini 1.5 Flashのリリース日は2024年5月である`

# あなたの分析結果
"""
            response = await self.chat_model.generate_content_async(consolidation_prompt)
            fact_to_remember = response.text.strip()

            if fact_to_remember != 'None' and fact_to_remember:
                print(f"[Memory Consolidation] Fact to remember for user {user_id}: {fact_to_remember}")
                embedding = await self._get_embedding(fact_to_remember)
                if embedding is None:
                    print("[Memory Consolidation] Failed to get embedding.")
                    return
                memory = load_memory()
                if user_id not in memory['users']:
                    memory['users'][user_id] = {'notes': []}
                if not any(n['text'] == fact_to_remember for n in memory['users'][user_id]['notes']):
                    memory['users'][user_id]['notes'].append({'text': fact_to_remember, 'embedding': embedding})
                    save_memory(memory)
                    print(f"[Memory Consolidation] Saved new fact for user {user_id}.")
                else:
                    print(f"[Memory Consolidation] Fact already exists for user {user_id}.")
        except Exception as e:
            print(f"An error occurred during memory consolidation: {e}")
        
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: return

        if self.bot.user.mentioned_in(message):
            async with message.channel.typing():
                user_id = str(message.author.id)
                user_message = message.content.replace(f'<@!{self.bot.user.id}>', '').strip()
                channel_id = message.channel.id
                history_text = "\n".join(conversation_history.get(channel_id, []))
                
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
                    
                    search_items = utils.google_search(search_query) 
                    
                    if isinstance(search_items, str) or not search_items:
                        await message.channel.send(search_items or "（検索したけど、何も見つからなかったわ。アンタの検索ワードがザコなんじゃない？）"); return

                    scraped_text = utils.scrape_url(search_items[0].get('link', ''))
                    search_summary = "\n".join([f"- {item.get('title', '')}" for item in search_items])
                    
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

                    if channel_id not in conversation_history: conversation_history[channel_id] = []
                    conversation_history[channel_id].append(f"ユーザー「{message.author.display_name}」: {user_message}")
                    conversation_history[channel_id].append(f"アタシ: {bot_response_text}")
                    if len(conversation_history[channel_id]) > 10:
                        conversation_history[channel_id] = conversation_history[channel_id][-10:]
                    
                    if not decision.startswith('SEARCH|'):
                        asyncio.create_task(self.process_memory_consolidation(message, user_message, bot_response_text))

                except Exception as e:
                    await message.channel.send(f"（うぅ…アタシの頭脳がショートしたわ…アンタのせいよ！: {e}）")
            return

        if not message.content.startswith(self.bot.command_prefix):
            if await self.handle_keywords(message):
                return

async def setup(bot):
    await bot.add_cog(AIChat(bot))
