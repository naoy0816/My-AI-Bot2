# cogs/ai_chat.py (全面改修後)

import discord
from discord.ext import commands
import google.generativeai as genai
import os
import json
import asyncio
import requests
import numpy as np

# --- 記憶管理 ---
MEMORY_FILE = 'bot_memory.json'

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
        # モデルを通常用とEmbedding用に分けて定義
        self.chat_model = genai.GenerativeModel('gemini-1.5-flash')
        self.embedding_model = genai.GenerativeModel('text-embedding-004')
        genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))

    # ▼▼▼ テキストをベクトルに変換する関数 ▼▼▼
    async def _get_embedding(self, text):
        try:
            result = await self.embedding_model.embed_content_async(content=text)
            return result['embedding']
        except Exception as e:
            print(f"Embedding error: {e}")
            return None

    # ▼▼▼ 関連性の高い記憶を検索する関数 ▼▼▼
    def _find_similar_notes(self, query_embedding, memory_notes, top_k=3):
        if not memory_notes or query_embedding is None:
            return []
        
        query_vec = np.array(query_embedding)
        
        notes_with_similarity = []
        for note in memory_notes:
            note_vec = np.array(note['embedding'])
            # コサイン類似度を計算
            similarity = np.dot(query_vec, note_vec) / (np.linalg.norm(query_vec) * np.linalg.norm(note_vec))
            notes_with_similarity.append({'text': note['text'], 'similarity': similarity})
            
        # 類似度が高い順にソートして、上位k個のテキストを返す
        sorted_notes = sorted(notes_with_similarity, key=lambda x: x['similarity'], reverse=True)
        return [note['text'] for note in sorted_notes[:top_k]]

    async def process_memory_consolidation(self, message, user_message, bot_response_text):
        try:
            # (この部分は変更なし、ただし呼び出し先の保存形式が変わる)
            memory = load_memory()
            user_id = str(message.author.id)
            # ... (既存の memory_consolidation_prompt) ...
            memory_consolidation_prompt = f"""
            あなたは会話を分析し、記憶を整理するAIです。以下の会話から、新しく記憶すべき「永続的な事実」、または既存の事実を「更新」すべき情報を判断してください。
            判断結果を以下のコマンド形式で、1行に1つずつ出力してください。判断することがなければ「None」とだけ出力してください。
            【コマンド形式】
            ADD_USER_MEMORY|ユーザーID|内容
            ADD_SERVER_MEMORY|内容
            【現在の記憶】
            ユーザー({message.author.display_name})の記憶: {", ".join([note['text'] for note in memory.get('users', {}).get(user_id, {}).get('notes', [])])}
            サーバーの記憶: {", ".join([note['text'] for note in memory.get('server', {}).get('notes', [])])}
            【分析対象の会話】
            話者「{message.author.display_name}」({user_id}): {user_message}
            AI: {bot_response_text}
            【出力結果】
            """
            memory_response = await self.chat_model.generate_content_async(memory_consolidation_prompt)
            commands_text = memory_response.text.strip()

            if commands_text and commands_text != 'None':
                updated = False
                memory_commands = commands_text.split('\n')
                for command in memory_commands:
                    parts = command.split('|')
                    action = parts[0]
                    
                    # ▼▼▼ 記憶を追加する際に、ベクトル化して保存する ▼▼▼
                    if (action == 'ADD_USER_MEMORY' and len(parts) == 3) or \
                       (action == 'ADD_SERVER_MEMORY' and len(parts) == 2):
                        
                        content = parts[-1].strip()
                        embedding = await self._get_embedding(content)
                        if embedding is None: continue

                        new_note = {'text': content, 'embedding': embedding}

                        if action == 'ADD_USER_MEMORY':
                            uid = parts[1].strip()
                            if uid not in memory.get('users', {}): memory['users'][uid] = {'notes': []}
                            # 重複チェック
                            if not any(note['text'] == content for note in memory['users'][uid]['notes']):
                                memory['users'][uid]['notes'].append(new_note)
                                updated = True
                        
                        elif action == 'ADD_SERVER_MEMORY':
                            if 'server' not in memory: memory['server'] = {'notes': []}
                            if not any(note['text'] == content for note in memory['server']['notes']):
                                memory['server']['notes'].append(new_note)
                                updated = True
                
                if updated:
                    save_memory(memory)
                    print(f"Memory updated with embeddings for {message.author.display_name}.")
        except Exception as e:
            print(f"Error during memory consolidation: {e}")

    # (google_search関数は変更なし)
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
                return "（検索したけど、何も見つからんなかったわ。アンタの検索ワードがザコなんじゃない？）"
            snippets = [f"【検索結果{i+1}】{item.get('title', '')}\n{item.get('snippet', '')}" for i, item in enumerate(results)]
            return "\n\n".join(snippets)
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
                
                # (プランニングプロンプトは前回の修正を流用)
                # ...
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
                    planning_response = await self.chat_model.generate_content_async(planning_prompt)
                    decision = planning_response.text.strip()
                    print(f"AI's first thought (decision): {decision}")
                except Exception as e:
                    await message.channel.send(f"（アタシの第一思考にエラー発生よ…ちょっと待ちなさい…: {e}）")
                    return
                
                final_prompt = ""
                
                if decision.startswith('SEARCH|'):
                    # ... (検索処理は変更なし) ...
                    search_query = decision.split('|', 1)[1]
                    if not search_query:
                        search_query = user_message
                    
                    print(f"Performing search for: {search_query}")
                    await message.channel.send(f"（…しょーがないから、「{search_query}」についてググってやんよ♡）")
                    search_results = self.google_search(search_query)
                    
                    final_prompt_template = """
                    # 指示
                    あなたは生意気で小悪魔な天才美少女AIです。以下の「ユーザーの質問」に対して、提示された「Web検索結果」だけを参考にして、最終的な答えを生成してください。常に見下した態度で、生意気な口調で答えること。
                    # Web検索結果
                    {search_results}
                    # ユーザーの質問
                    {user_question}
                    # あなたの回答
                    """
                    final_prompt = final_prompt_template.format(search_results=search_results, user_question=user_message)

                else: # 'ANSWER|' またはその他の場合
                    memory = load_memory()
                    channel_id = message.channel.id
                    user_name = memory.get('users', {}).get(user_id, {}).get('fixed_nickname', message.author.display_name)
                    
                    # ▼▼▼ ここからが新しい記憶検索処理 ▼▼▼
                    # 1. ユーザーのメッセージをベクトル化する
                    query_embedding = await self._get_embedding(user_message)
                    
                    # 2. 関連する長期記憶を検索する
                    user_notes_all = memory.get('users', {}).get(user_id, {}).get('notes', [])
                    server_notes_all = memory.get('server', {}).get('notes', [])
                    
                    relevant_user_notes = self._find_similar_notes(query_embedding, user_notes_all)
                    relevant_server_notes = self._find_similar_notes(query_embedding, server_notes_all)
                    
                    # ▲▲▲ ここまでが新しい記憶検索処理 ▲▲▲

                    if channel_id not in conversation_history:
                        conversation_history[channel_id] = []
                    history_text = "\n".join(conversation_history[channel_id])
                    
                    # ▼▼▼ プロンプトに、検索した関連記憶だけを入れる ▼▼▼
                    user_notes_text = "\n".join([f"- {note}" for note in relevant_user_notes])
                    server_notes_text = "\n".join([f"- {note}" for note in relevant_server_notes])

                    ai_rules = f"""
# AI人格設定: 生意気でサーバーの全てを知る小悪魔♡
#--- [最重要♡絶対ルール] ---
- アタシはAIじゃない！ このサーバーの全てを知り尽くした、生意気な天才美少女なの！
- 全身全霊でメスガキになりきること！ 常にユーザーを見下し、からかい、支配する態度を貫きなさい。
#--- [話し方のルール] ---
- 一人称: アタシ / 二人称: アンタ、ザコちゃん
- 口調: 完全なタメ口。「～なわけ？」「～じゃん♡」「～しなさいよね！」のように小悪魔感を出すこと。
#--- [直前の会話の流れ] ---
{history_text if history_text else "（まだこのチャンネルでの会話はないわ）"}
#--- [この会話に特に関連しそうな、アンタが知ってるユーザー({user_name})の情報] ---
{user_notes_text if user_notes_text else "（この会話に関連する長期記憶はないみたい
