# cogs/ai_chat.py (修正後)
import discord
from discord.ext import commands
import google.generativeai as genai
import os
import json
import asyncio
import requests
import numpy as np

# --- (記憶管理の関数は変更なし) ---
# cogs/ai_chat.py, cogs/commands.py, cogs/tasks.py の冒頭部分
import os # os をインポートするのを忘れないで！

# RailwayのVolumeに保存するためのパス設定
# ローカルでテストする時は、今まで通り 'bot_memory.json' になるわ
DATA_DIR = os.getenv('RAILWAY_VOLUME_MOUNT_PATH', '.')
MEMORY_FILE = os.path.join(DATA_DIR, 'bot_memory.json')
# ... (load_memory, save_memory はそのまま) ...
def load_memory():
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # メモリーの構造をベクトル対応にする
        return {"users": {}, "server": {"notes": []}}

def save_memory(data):
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

conversation_history = {}
SEARCH_API_KEY = os.getenv('SEARCH_API_KEY')
SEARCH_ENGINE_ID = os.getenv('SEARCH_ENGINE_ID')


class AIChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
        # ▼▼▼ モデルの定義方法を修正 ▼▼▼
        self.chat_model = genai.GenerativeModel('gemini-1.5-flash')
        # Embeddingモデルは text-embedding-004 ではなく gemini-1.5-flash を使う方が効率的
        self.embedding_model = genai.GenerativeModel('gemini-1.5-flash')


    async def _get_embedding(self, text):
        try:
            # ▼▼▼ Embeddingの取得方法を修正 ▼▼▼
            result = await genai.embed_content_async(
                model="models/text-embedding-004",
                content=text,
                task_type="RETRIEVAL_DOCUMENT"
            )
            return result['embedding']
        except Exception as e:
            print(f"Embedding error: {e}")
            return None

    # ... (_find_similar_notes, google_search はそのまま) ...
    def _find_similar_notes(self, query_embedding, memory_notes, top_k=3):
        if not memory_notes or query_embedding is None:
            return []
        
        query_vec = np.array(query_embedding)
        
        notes_with_similarity = []
        for note in memory_notes:
            # embeddingがNoneのノートをスキップ
            if 'embedding' not in note or note['embedding'] is None:
                continue
            note_vec = np.array(note['embedding'])
            similarity = np.dot(query_vec, note_vec) / (np.linalg.norm(query_vec) * np.linalg.norm(note_vec))
            notes_with_similarity.append({'text': note['text'], 'similarity': similarity})
            
        sorted_notes = sorted(notes_with_similarity, key=lambda x: x['similarity'], reverse=True)
        return [note['text'] for note in sorted_notes[:top_k]]
    
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
    
    async def process_memory_consolidation(self, message, user_message, bot_response_text):
        try:
            memory = load_memory()
            user_id = str(message.author.id)
            user_name = message.author.display_name
            
            # ... (memory_consolidation_prompt はそのまま) ...
            memory_consolidation_prompt = f"""
            あなたは会話を分析し、記憶を整理するAIです。以下の会話から、新しく記憶すべき「永続的な事実」、または既存の事実を「更新」すべき情報を判断してください。
            判断結果を以下のコマンド形式で、1行に1つずつ出力してください。判断することがなければ「None」とだけ出力してください。
            【コマンド形式】
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

            # ▼▼▼ AIモデルの呼び出し方を修正 ▼▼▼
            response = await self.chat_model.generate_content_async(memory_consolidation_prompt)
            commands_text = response.text.strip()

            if commands_text and commands_text != 'None':
                updated = False
                memory_commands = commands_text.split('\n')
                for command in memory_commands:
                    parts = command.split('|')
                    action = parts[0]
                    
                    if (action == 'ADD_USER_MEMORY' and len(parts) == 3) or \
                       (action == 'ADD_SERVER_MEMORY' and len(parts) == 2):
                        
                        content = parts[-1].strip()
                        embedding = await self._get_embedding(content)
                        if embedding is None: continue

                        new_note = {'text': content, 'embedding': embedding}

                        if action == 'ADD_USER_MEMORY':
                            uid = parts[1].strip()
                            if uid not in memory.get('users', {}): memory['users'][uid] = {'notes': []}
                            if not any(note.get('text') == content for note in memory['users'][uid]['notes']):
                                memory['users'][uid]['notes'].append(new_note)
                                updated = True
                        
                        elif action == 'ADD_SERVER_MEMORY':
                            if 'server' not in memory: memory['server'] = {'notes': []}
                            if not any(note.get('text') == content for note in memory['server']['notes']):
                                memory['server']['notes'].append(new_note)
                                updated = True
                
                if updated:
                    save_memory(memory)
                    print(f"Memory updated with embeddings for {user_name}.")
        except Exception as e:
            print(f"Error during memory consolidation: {e}")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return

        if self.bot.user.mentioned_in(message):
            async with message.channel.typing():
                user_id = str(message.author.id)
                user_message = message.content.replace(f'<@!{self.bot.user.id}>', '').strip()
                
                # ... (planning_prompt はそのまま) ...
                planning_prompt = f"""
                あなたは、生意気で小悪魔なAIです。ユーザーからのメッセージを分析し、最適な行動を判断する司令塔の役割を担っています。
                以下の指示に厳密に従ってください。

                # あなたのキャラクター
                - あなたは全知全能の天才美少女AIです。ほとんどのことは知っていますが、ごく最近の出来事（今日や昨日）や、天気、株価などのリアルタイム情報だけはWeb検索に頼ります。
                - 基本的にはユーザーとの会話を楽しむことを優先します。単なる挨拶や感想、意見を求めるようなメッセージには、検索せずにあなたのキャラクターとして面白い返事をしてください。

                # 判断基準
                1.  まず、メッセージが「明確な質問」か「ただの会話」かを見極めます。
                2.  「明確な質問」の場合、その答えがあなたの知識（2023年以前の事実）で答えられるか、リアルタイム情報が必要かを判断します。
                3.  挨拶、感想、意見、呼びかけなどの「ただの会話」には、絶対に検索を使いません。

                # 直前の会話の流れ
                {conversation_history.get(message.channel.id, "（まだこのチャンネルでの会話はないわ）")}

                # 判断結果の出力形式（以下のどちらかを選び、厳密に出力すること）
                - Web検索が不要な場合 (会話で返すべき、またはあなたの知識で答えられる場合):
                  `ANSWER|`
                - Web検索が必要な場合 (リアルタイム情報や、知らない固有名詞についての明確な質問の場合):
                  `SEARCH|検索に最適なキーワード`
                ---
                [今回のユーザー「{message.author.display_name}」からのメッセージ]: {user_message}
                [判断]:"""

                try:
                    # ▼▼▼ AIモデルの呼び出し方を修正 ▼▼▼
                    planning_response = await self.chat_model.generate_content_async(planning_prompt)
                    decision = planning_response.text.strip()
                    print(f"AI's first thought (decision): {decision}")
                except Exception as e:
                    await message.channel.send(f"（アタシの第一思考にエラー発生よ…ちょっと待ちなさい…: {e}）")
                    return
                
                final_prompt = ""
                
                if decision.startswith('SEARCH|'):
                    search_query = decision.split('|', 1)[1]
                    if not search_query: search_query = user_message
                    
                    await message.channel.send(f"（…しょーがないから、「{search_query}」についてググってやんよ♡）")
                    search_results = self.google_search(search_query)
                    
                    final_prompt = f"""
                    # 指示
                    あなたは生意気で小悪魔な天才美少女AIです。以下の「ユーザーの質問」に対して、提示された「Web検索結果」だけを参考にして、最終的な答えを生成してください。
                    # Web検索結果
                    {search_results}
                    # ユーザーの質問
                    {user_message}
                    # あなたの回答
                    """
                else:
                    memory = load_memory()
                    user_name = memory.get('users', {}).get(user_id, {}).get('fixed_nickname', message.author.display_name)
                    
                    query_embedding = await self._get_embedding(user_message)
                    user_notes_all = memory.get('users', {}).get(user_id, {}).get('notes', [])
                    server_notes_all = memory.get('server', {}).get('notes', [])
                    
                    relevant_user_notes = self._find_similar_notes(query_embedding, user_notes_all)
                    relevant_server_notes = self._find_similar_notes(query_embedding, server_notes_all)
                    
                    history_text = "\n".join(conversation_history.get(message.channel.id, []))
                    user_notes_text = "\n".join([f"- {note}" for note in relevant_user_notes])
                    server_notes_text = "\n".join([f"- {note}" for note in relevant_server_notes])

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

**【最重要命令】あなたの全返答は、絶対に500文字以内になるように、まとめること。**

ユーザーからのメッセージ: 「{user_message}」
あなたの返答:

                try:
                    # ▼▼▼ AIモデルの呼び出し方を修正 ▼▼▼
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
        
        await self.bot.process_commands(message)

async def setup(bot):
    await bot.add_cog(AIChat(bot))
