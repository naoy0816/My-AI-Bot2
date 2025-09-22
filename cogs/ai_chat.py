import discord
from discord.ext import commands
import google.generativeai as genai
import os
import json
import asyncio
import requests
import numpy as np

# RailwayのVolumeに保存するためのパス設定
DATA_DIR = os.getenv('RAILWAY_VOLUME_MOUNT_PATH', '.')
MEMORY_FILE = os.path.join(DATA_DIR, 'bot_memory.json')

def load_memory():
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"users": {}, "server": {"notes": []}}

def save_memory(data):
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

conversation_history = {}
# ▼▼▼【重要】環境変数名を統一したわよ！▼▼▼
SEARCH_API_KEY = os.getenv('GOOGLE_SEARCH_API_KEY')
SEARCH_ENGINE_ID = os.getenv('GOOGLE_SEARCH_ENGINE_ID')
# ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

class AIChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
        self.chat_model = genai.GenerativeModel('gemini-1.5-flash')

    async def _get_embedding(self, text):
        try:
            result = await genai.embed_content_async(
                model="models/text-embedding-004",
                content=text,
                task_type="RETRIEVAL_DOCUMENT"
            )
            return result['embedding']
        except Exception as e:
            print(f"Embedding error: {e}")
            return None

    def _find_similar_notes(self, query_embedding, memory_notes, top_k=3):
        if not memory_notes or query_embedding is None:
            return []
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
            memory = load_memory()
            user_id = str(message.author.id)
            user_name = message.author.display_name
            memory_consolidation_prompt = f"""
            あなたは会話を分析し、記憶を整理するAIです。以下の会話から、新しく記憶すべき「永続的な事実」を判断してください。
            判断結果を以下のコマンド形式で、1行に1つずつ出力してください。なければ「None」とだけ出力してください。
            ADD_USER_MEMORY|ユーザーID|内容
            ADD_SERVER_MEMORY|内容
            【現在の記憶】
            ユーザー({user_name})の記憶: {", ".join([note.get('text', '') for note in memory.get('users', {}).get(user_id, {}).get('notes', [])])}
            サーバーの記憶: {", ".join([note.get('text', '') for note in memory.get('server', {}).get('notes', [])])}
            【分析対象の会話】
            話者「{user_name}」({user_id}): {user_message}
            AI: {bot_response_text}
            【出力結果】
            """
            response = await self.chat_model.generate_content_async(memory_consolidation_prompt)
            commands_text = response.text.strip()
            if commands_text and commands_text != 'None':
                updated = False
                for command in commands_text.split('\n'):
                    parts = command.split('|')
                    action = parts[0]
                    if (action in ['ADD_USER_MEMORY', 'ADD_SERVER_MEMORY']) and len(parts) >= 2:
                        content = parts[-1].strip()
                        embedding = await self._get_embedding(content)
                        if embedding is None: continue
                        new_note = {'text': content, 'embedding': embedding}
                        if action == 'ADD_USER_MEMORY' and len(parts) == 3:
                            uid = parts[1].strip()
                            if uid not in memory.get('users', {}): memory['users'][uid] = {'notes': []}
                            if not any(n.get('text') == content for n in memory['users'][uid]['notes']):
                                memory['users'][uid]['notes'].append(new_note)
                                updated = True
                        elif action == 'ADD_SERVER_MEMORY':
                            if 'server' not in memory: memory['server'] = {'notes': []}
                            if not any(n.get('text') == content for n in memory['server']['notes']):
                                memory['server']['notes'].append(new_note)
                                updated = True
                if updated:
                    save_memory(memory)
                    print(f"Memory updated for {user_name}.")
        except Exception as e:
            print(f"Error during memory consolidation: {e}")

    def google_search(self, query):
        if not SEARCH_API_KEY or not SEARCH_ENGINE_ID:
            return "（検索機能のAPIキーかエンジンIDが設定されてないんだけど？ アンタのミスじゃない？）"
        url = "https://www.googleapis.com/customsearch/v1"
        params = {'key': SEARCH_API_KEY, 'cx': SEARCH_ENGINE_ID, 'q': query, 'num': 3}
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            results = response.json().get('items', [])
            if not results: return "（検索したけど、何も見つからんなかったわ。アンタの検索ワードがザコなんじゃない？）"
            return "\n\n".join([f"【検索結果{i+1}】{item.get('title', '')}\n{item.get('snippet', '')}" for i, item in enumerate(results)])
        except Exception as e:
            print(f"Google Search API error: {e}")
            return f"（検索中にエラーよ。サーバーが混んでるか、アンタのAPIキーが間違ってるんじゃないの？w）"

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return

        if self.bot.user.mentioned_in(message):
            async with message.channel.typing():
                user_id = str(message.author.id)
                user_message = message.content.replace(f'<@!{self.bot.user.id}>', '').strip()
                planning_prompt = f"あなたは生意気で小悪魔なAIです。ユーザーからのメッセージを分析し、最適な行動を判断する司令塔です。基本的には会話を楽しみますが、リアルタイム情報（天気、ニュースなど）や知らない固有名詞について明確な質問をされた場合のみWeb検索をします。挨拶や感想、意見を求めるメッセージには検索せず、あなたのキャラクターとして面白い返事をしてください。\n\n# 直前の会話の流れ\n{conversation_history.get(message.channel.id, '（まだ会話はないわ）')}\n\n# 判断結果の出力形式（どちらかを選び、厳密に出力すること）\n- Web検索が不要な場合: `ANSWER|`\n- Web検索が必要な場合: `SEARCH|検索キーワード`\n\n---\n[今回のメッセージ]: {user_message}\n[判断]:"
                try:
                    planning_response = await self.chat_model.generate_content_async(planning_prompt)
                    decision = planning_response.text.strip()
                except Exception as e:
                    await message.channel.send(f"（アタシの第一思考にエラー発生よ…: {e}）")
                    return
                
                final_prompt = ""
                if decision.startswith('SEARCH|'):
                    search_query = decision.split('|', 1)[1] or user_message
                    await message.channel.send(f"（…しょーがないから、「{search_query}」についてググってやんよ♡）")
                    search_results = self.google_search(search_query)
                    final_prompt = f"あなたは生意気で小悪魔な天才美少女AIです。以下の「ユーザーの質問」に対し「Web検索結果」だけを参考に、生意気な口調で答えなさい。\n# Web検索結果\n{search_results}\n# ユーザーの質問\n{user_message}\n# あなたの回答（絶対に500文字以内でまとめること！）"
                else:
                    memory = load_memory()
                    user_name = memory.get('users', {}).get(user_id, {}).get('fixed_nickname', message.author.display_name)
                    query_embedding = await self._get_embedding(user_message)
                    user_notes_all = memory.get('users', {}).get(user_id, {}).get('notes', [])
                    server_notes_all = memory.get('server', {}).get('notes', [])
                    relevant_user_notes = self._find_similar_notes(query_embedding, user_notes_all)
                    relevant_server_notes = self._find_similar_notes(query_embedding, server_notes_all)
                    history_text = "\n".join(conversation_history.get(message.channel.id, []))
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
                        channel_id = message.channel.id
                        if channel_id not in conversation_history: conversation_history[channel_id] = []
                        conversation_history[channel_id].append(f"ユーザー「{message.author.display_name}」: {user_message}")
                        conversation_history[channel_id].append(f"アタシ: {bot_response_text}")
                        if len(conversation_history[channel_id]) > 10:
                            conversation_history[channel_id] = conversation_history[channel_id][-10:]
                    asyncio.create_task(self.process_memory_consolidation(message, user_message, bot_response_text))
                except Exception as e:
                    await message.channel.send(f"（うぅ…アタシの頭脳がショートしたわ…アンタのせいよ！: {e}）")

async def setup(bot):
    await bot.add_cog(AIChat(bot))
