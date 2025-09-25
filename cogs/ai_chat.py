# cogs/ai_chat.py (最終完全版 - 神の視点モード搭載)
import discord
from discord.ext import commands
import google.generativeai as genai
import os
import json
import asyncio
import numpy as np
import time
import re
from collections import deque
import requests
from . import _utils as utils
from . import _persona_manager as persona_manager

# -------------------- 設定項目 --------------------
ENABLE_PROACTIVE_INTERVENTION = True
INTERVENTION_THRESHOLD = 0.78
INTERVENTION_COOLDOWN = 300
# ------------------------------------------------

# ファイルパス設定
DATA_DIR = os.getenv('RAILWAY_VOLUME_MOUNT_PATH', '.')
MEMORY_FILE = os.path.join(DATA_DIR, 'bot_memory.json')
MOOD_FILE = os.path.join(DATA_DIR, 'channel_mood.json')

def load_memory():
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            memory = json.load(f)
            if 'relationships' not in memory: memory['relationships'] = {}
            return memory
    except (FileNotFoundError, json.JSONDecodeError):
        return {"users": {}, "server": {"notes": [], "relationships": {}}}

def save_memory(data):
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_mood_data():
    try:
        with open(MOOD_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_mood_data(data):
    with open(MOOD_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

conversation_history = {}
last_intervention_time = {}
recent_messages = {}

class AIChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        self.db_manager = None

    @commands.Cog.listener()
    async def on_ready(self):
        self.db_manager = self.bot.get_cog('DatabaseManager')
        if self.db_manager:
            print("Successfully linked with DatabaseManager.")
        else:
            print("Warning: DatabaseManager cog not found.")

    async def handle_keywords(self, message):
        content = message.content
        responses = { 'おはよう': 'おはよ♡ アンタも朝から元気なワケ？w', 'おやすみ': 'ふん、せいぜい良い夢でも見なさいよね！ザコちゃん♡', 'すごい': 'あっはは！当然でしょ？アタシを誰だと思ってんのよ♡', '天才': 'あっはは！当然でしょ？アタシを誰だと思ってんのよ♡', 'ありがとう': 'べ、別にアンタのためにやったんじゃないんだからね！勘違いしないでよね！', '感謝': 'べ、別にアンタのためにやったんじゃないんだからね！勘違いしないでよね！', '疲れた': 'はぁ？ザコすぎw もっとしっかりしなさいよね！', 'しんどい': 'はぁ？ザコすぎw もっとしっかりしなさいよね！',  'かわいい': 'ふ、ふーん…。まぁ、アンタがアタシの魅力に気づくのは当然だけど？♡', 'ｗ': '何笑ってんのよ、キモチワルイんだけど？', '笑': '何笑ってんのよ、キモチワルイんだけど？', 'ごめん': 'わかればいいのよ、わかれば。次はないかんね？', 'すまん': 'わかればいいのよ、わかれば。次はないかんね？', '何してる': 'アンタには関係ないでしょ。アタシはアンタと違って忙しいの！', 'なにしてる': 'アンタには関係ないでしょ。アタシはアンタと違って忙しいの！', 'お腹すいた': '自分でなんとかしなさいよね！アタシはアンタのママじゃないんだけど？', 'はらへった': '自分でなんとかしなさいよね！アタシはアンタのママじゃないんだけど？',}
        for keyword, response in responses.items():
            if keyword in content: await message.channel.send(response); return True
        return False

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
        return sorted_notes[:top_k]

    async def process_memory_consolidation(self, message, user_message, bot_response_text):
        try:
            user_id = str(message.author.id)
            user_name = message.author.display_name
            consolidation_prompt = f"""
あなたは会話を分析し、長期記憶に保存すべき重要な事実を抽出するAIです。
# 分析対象の会話
ユーザー「{user_name}」: {user_message}
アタシ: {bot_response_text}
# 指示
この会話に、ユーザー({user_name})に関する新しい個人的な情報（好み、名前、目標、過去の経験など）や、後で会話に役立ちそうな重要な事実が含まれていますか？含まれている場合、その事実を「{user_name}は〇〇」という簡潔な三人称の文章で抽出しなさい。そうでなければ「None」と出力しなさい。
"""
            response = await self.model.generate_content_async(consolidation_prompt)
            fact_to_remember = response.text.strip()
            if fact_to_remember != 'None' and fact_to_remember:
                embedding = await utils.get_embedding(fact_to_remember)
                if embedding is None: return
                memory = load_memory()
                if user_id not in memory['users']: memory['users'][user_id] = {'notes': []}
                if not any(n['text'] == fact_to_remember for n in memory['users'][user_id]['notes']):
                    memory['users'][user_id]['notes'].append({'text': fact_to_remember, 'embedding': embedding})
                    save_memory(memory)
        except Exception as e: print(f"An error occurred during memory consolidation: {e}")

    async def process_user_interaction(self, message):
        try:
            channel_id = message.channel.id
            author_id = str(message.author.id)
            if channel_id not in recent_messages or not recent_messages[channel_id]: return
            interaction_partners = {str(msg['author_id']) for msg in recent_messages[channel_id] if str(msg['author_id']) != author_id}
            if not interaction_partners: return
            context = "\n".join([f"{msg['author_name']}: {msg['content']}" for msg in recent_messages[channel_id]])
            for partner_id in interaction_partners:
                interaction_prompt = f"以下の会話の中心的なトピックを単語で抽出しなさい(例:ゲーム,アニメ)。不明ならNoneと出力。\n\n{context}"
                response = await self.model.generate_content_async(interaction_prompt)
                topic = response.text.strip()
                if topic != 'None' and topic:
                    memory = load_memory()
                    for u1, u2 in [(author_id, partner_id), (partner_id, author_id)]:
                        if u1 not in memory['relationships']: memory['relationships'][u1] = {}
                        if u2 not in memory['relationships'][u1]: memory['relationships'][u1][u2] = {'topics': {}, 'interaction_count': 0}
                        memory['relationships'][u1][u2]['topics'][topic] = memory['relationships'][u1][u2]['topics'].get(topic, 0) + 1
                        memory['relationships'][u1][u2]['interaction_count'] += 1
                    save_memory(memory)
        except Exception as e: print(f"An error occurred during user interaction processing: {e}")

    async def analyze_and_track_mood(self, message: discord.Message):
        try:
            analysis_prompt = f"""
以下のユーザーの発言を分析し、発言の感情を「Positive」「Negative」「Neutral」のいずれかで判定し、-1.0から1.0の範囲で感情スコアを付けなさい。
ユーザーの発言: 「{message.content}」

出力形式は必ず以下の厳密なJSON形式とすること。
{{
  "emotion": "判定結果",
  "score": スコア
}}
"""
            response = await self.model.generate_content_async(analysis_prompt)
            json_match = re.search(r'```json\n({.*?})\n```', response.text, re.DOTALL) or re.search(r'({.*?})', response.text, re.DOTALL)
            if json_match:
                analysis_result = json.loads(json_match.group(1))
                score = float(analysis_result.get("score", 0.0))
                channel_id = str(message.channel.id)
                mood_data = load_mood_data()
                if channel_id not in mood_data: mood_data[channel_id] = {"scores": [], "average": 0.0}
                scores = mood_data[channel_id].get("scores", [])
                scores.append(score)
                mood_data[channel_id]["scores"] = scores[-10:]
                mood_data[channel_id]["average"] = round(np.mean(mood_data[channel_id]["scores"]), 4)
                save_mood_data(mood_data)
        except Exception as e:
            print(f"An error occurred during mood analysis: {e}")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or message.content.startswith(self.bot.command_prefix): return
        
        asyncio.create_task(self.analyze_and_track_mood(message))
        if self.db_manager:
            asyncio.create_task(self.db_manager.add_message_to_db(message))

        channel_id = message.channel.id
        if channel_id not in recent_messages: recent_messages[channel_id] = deque(maxlen=6)
        recent_messages[channel_id].append({'author_id': message.author.id, 'author_name': message.author.display_name, 'content': message.content})
        asyncio.create_task(self.process_user_interaction(message))
        
        if self.bot.user.mentioned_in(message):
            if message.attachments:
                await self.handle_multimodal_mention(message)
            else:
                await self.handle_text_mention(message)
            return

        if await self.handle_keywords(message): return
        
        if ENABLE_PROACTIVE_INTERVENTION:
            now = time.time()
            if (now - last_intervention_time.get(channel_id, 0)) < INTERVENTION_COOLDOWN: return
            if len(message.content) < 10: return
            query_embedding = await utils.get_embedding(message.content)
            if query_embedding is None: return
            memory = load_memory()
            all_notes = [note for user in memory['users'].values() for note in user['notes']] + memory['server']['notes']
            if not all_notes: return
            most_relevant_note = self._find_similar_notes(query_embedding, all_notes, top_k=1)
            if most_relevant_note and most_relevant_note[0]['similarity'] > INTERVENTION_THRESHOLD:
                relevant_fact = most_relevant_note[0]['text']
                await self.handle_proactive_intervention(message, relevant_fact)

    async def handle_multimodal_mention(self, message):
        user_message = message.content.replace(f'<@!{self.bot.user.id}>', '').strip()
        attachment = message.attachments[0]
        user_name = message.author.display_name
        
        persona = utils.get_current_persona()
        if not persona: await message.channel.send("（ペルソナファイルが読み込めないんだけど…！）"); return

        if not (attachment.content_type and (attachment.content_type.startswith('image/') or attachment.content_type.startswith('video/'))):
            await message.channel.send("はぁ？ アタシに見せたいなら、画像か動画にしなさいよね！")
            return

        async with message.channel.typing():
            try:
                file_data = await attachment.read()
                media_blob = {"mime_type": attachment.content_type, "data": file_data}
                multimodal_prompt_template = persona["settings"].get("multimodal_prompt", "# 指示\nメディアを見て応答しなさい。")
                char_settings = persona["settings"].get("char_settings", "").format(user_name=user_name)
                prompt_parts = [f"{char_settings}\n{multimodal_prompt_template}\n\n# ユーザーのテキスト\n「{user_message or '（…無言でコレをアタシに見せてきたわ）'}」\n\n# あなたの応答:", media_blob]
                
                multimodal_model = genai.GenerativeModel('gemini-1.5-pro')
                response = await multimodal_model.generate_content_async(prompt_parts)
                await message.channel.send(response.text)
            except Exception as e:
                await message.channel.send(f"（うぅ…アンタのファイルを見ようとしたら、アタシの目がぁぁ…！: {e}）")

    async def handle_text_mention(self, message):
        async with message.channel.typing():
            user_message = message.content.replace(f'<@!{self.bot.user.id}>', '').strip()
            persona = utils.get_current_persona()
            if not persona: await message.channel.send("（ペルソナファイルが読み込めないんだけど…！）"); return
            meta_thinking_prompt = self.build_meta_thinking_prompt(message, user_message, persona)
            try:
                response = await self.model.generate_content_async(meta_thinking_prompt)
                decision_data = self.parse_decision_text(response.text.strip())
            except Exception as e:
                await message.channel.send(f"（アタシの超思考回路にエラー発生よ…: {e}）"); return

            if decision_data.get("ACTION") == 'SEARCH':
                await self.execute_search_and_respond(message, user_message, decision_data.get("QUERY"), persona)
            else:
                target_user_id = decision_data.get("TARGET_USER_ID")
                final_prompt = await self.build_final_prompt(message, user_message, decision_data, persona, target_user_id)
                await self.generate_and_send_response(message, final_prompt, user_message, True)

    def build_meta_thinking_prompt(self, message, user_message, persona):
        mentioned_users_text = "（なし）"
        if message.mentions:
            mentioned_users_text = "\n".join([f"- {user.display_name} (ID: {user.id})" for user in message.mentions if not user.bot and user.id != self.bot.user.id])
        return f"""
あなたは、「{persona.get("name", "AI")}」({persona.get("description", "応答します。")})の思考を司る「メタAI」です。
ユーザーのメッセージを分析し、次の行動を【1回の思考で】決定してください。
# 思考プロセス
1. **意図と感情の分析:** ユーザーのメッセージ（「{user_message}」）を読み解き、真の意図と感情を把握する。
2. **【重要】特定人物に関する質問か判断:** メッセージは、特定のユーザーについて尋ねるものか？ メンションリストを参考に判断し、もしそうならそのユーザーのIDを特定する。そうでなければ `None` とする。
3. **行動決定:** 意図に基づき、取るべき行動を `SEARCH` (Web検索) か `ANSWER` (自己知識で応答) に決定する。
4. **戦略立案 (ANSWERの場合):** あなたの性格とユーザーの感情を考慮し、最適な応答戦略を `TEASE`, `SUMMARIZE_USER`, `HELP_RELUCTANTLY` などから選択する。
5. **クエリ/要点生成:**
    - `SEARCH` の場合: 最適な検索クエリを生成する。
    - `ANSWER` の場合: 応答に含めるべき重要な要点をリストアップする。
# 分析対象
- ユーザー名: {message.author.display_name}
- 会話履歴: {self.get_history_text(message.channel.id)}
- ユーザーのメッセージ: 「{user_message}」
- メッセージ内でメンションされたユーザー:
{mentioned_users_text}
# 出力形式
思考プロセスは出力せず、結果だけを以下の厳密な形式で出力すること。
[ACTION:決定した行動]
[QUERY:SEARCHの場合の検索クエリ]
[EMOTION:分析した感情]
[INTENT:分析した意図]
[STRATEGY:ANSWERの場合の応答戦略]
[POINTS:ANSWERの場合の要点（カンマ区切り）]
[TARGET_USER_ID:特定人物に関する質問の場合、そのユーザーのID。それ以外はNone]
"""

    def parse_decision_text(self, text):
        data = {}
        for line in text.splitlines():
            match = re.match(r'\[(.*?):(.*?)\]', line)
            if match:
                data[match.group(1)] = match.group(2).strip()
        return data

    def get_history_text(self, channel_id):
        return "\n".join(conversation_history.get(channel_id, [])) or "（まだこのチャンネルでの会話はないわ）"

    async def execute_search_and_respond(self, message, user_message, query, persona):
        if not query: await message.channel.send("（検索キーワードを思いつかなかったわ…）"); return
        await message.channel.send(f"（「{query}」でググって、中身まで読んでやんよ♡）")
        search_items = utils.google_search(query)
        if isinstance(search_items, str) or not search_items:
            await message.channel.send(search_items or "（検索したけど、何も見つからなかったわ。）"); return
        scraped_text = utils.scrape_url(search_items[0].get('link', ''))
        search_summary = "\n".join([f"- {item.get('title', '')}" for item in search_items])
        search_prompt_template = persona["settings"].get("search_prompt", "# 指示\n検索結果を元に応答しなさい。")
        final_prompt = f"{search_prompt_template}\n# 検索結果\n{search_summary}\n# Webページ本文\n{scraped_text}\n# ユーザーの質問\n{user_message}\n# あなたの回答:"
        await self.generate_and_send_response(message, final_prompt, user_message, False)

    async def build_final_prompt(self, message, user_message, decision_data, persona, target_user_id: str = None):
        user_id = str(message.author.id)
        memory = load_memory()
        user_name = memory.get('users', {}).get(user_id, {}).get('fixed_nickname', message.author.display_name)
        
        channel_id = str(message.channel.id)
        mood_data = load_mood_data().get(channel_id, {"average": 0.0})
        mood_score = mood_data["average"]
        mood_text = "ニュートラル"
        if mood_score > 0.2: mood_text = "ポジティブ"
        elif mood_score < -0.2: mood_text = "ネガティブ"

        prompt_heading = "【チャンネル内記憶】このチャンネルでの関連性の高い過去の会話ログ"
        if target_user_id and target_user_id.lower() != 'none':
            try:
                target_user_object = await self.bot.fetch_user(int(target_user_id))
                prompt_heading = f"【チャンネル内記憶】ユーザー「{target_user_object.display_name}」に関する過去の発言ログ"
                search_query = target_user_object.display_name
            except (discord.NotFound, ValueError):
                target_user_id, search_query = None, user_message
        else:
            target_user_id, search_query = None, user_message

        relevant_logs_text, cross_channel_logs_text = "（特になし）", "（特になし）"
        if self.db_manager:
            relevant_logs_text = await self.db_manager.search_similar_messages(search_query, str(message.channel.id), author_id=target_user_id)
            if not target_user_id:
                cross_channel_logs_text = await self.db_manager.search_across_all_channels(search_query, message.guild)
        
        query_embedding = await utils.get_embedding(user_message)
        user_notes_all = memory.get('users', {}).get(user_id, {}).get('notes', [])
        server_notes_all = memory.get('server', {}).get('notes', [])
        user_notes_text = "\n".join([f"- {n['text']}" for n in self._find_similar_notes(query_embedding, user_notes_all)]) or "（特になし）"
        server_notes_text = "\n".join([f"- {n['text']}" for n in self._find_similar_notes(query_embedding, server_notes_all)]) or "（特になし）"
        
        relationship_text = "（特になし）"
        if user_id in memory.get('relationships', {}):
            relations = [f"- { (await self.bot.fetch_user(int(p_id))).display_name }とは「{max(d['topics'], key=d['topics'].get) if d['topics'] else '色々な話'}」についてよく話している" for p_id, d in memory['relationships'][user_id].items()]
            if relations: relationship_text = "\n".join(relations)

        char_settings = persona["settings"].get("char_settings", "").format(user_name=user_name)
        return f"""{char_settings}
---
# ★★★ アタシの思考と応答戦略 ★★★
[EMOTION:{decision_data.get("EMOTION", "不明")}] [INTENT:{decision_data.get("INTENT", "不明")}] [STRATEGY:{decision_data.get("STRATEGY", "不明")}] [POINTS:{decision_data.get("POINTS", "特になし")}]
---
# 記憶情報（これらの情報を統合して、人間のように自然で文脈に合った応答を生成すること）
## 【最優先】現在のチャンネルの雰囲気
このチャンネルは現在、「{mood_text}」な雰囲気（ムードスコア: {mood_score:.2f}）です。この空気を読んで応答しなさい。
## {prompt_heading}
{relevant_logs_text}
## ★★★【サーバー横断記憶】サーバー全体の関連性の高い過去の会話ログ★★★
これは、他のチャンネルで行われた、今の会話に関連する可能性のある記憶です。もし関連があれば、自然な形で会話に組み込みなさい。（例：「そういえば、その話、昨日 #別のチャンネル で〇〇さんが言ってたわね…」）
{cross_channel_logs_text}
## 【参考】直前の会話
{self.get_history_text(message.channel.id)}
## 【参考】その他の知識
- ユーザー({user_name})に関する手動記憶(JSON): {user_notes_text}
- サーバー全体の共有知識(JSON): {server_notes_text}
- サーバーの人間関係: {relationship_text}
---
以上の全てを完璧に理解し、立案した「応答戦略」と「チャンネルの雰囲気」、「サーバー全体の記憶」に基づき、ユーザー `{user_name}` のメッセージ「{user_message}」に返信しなさい。
**【重要】** もしこれが特定のユーザーに関する質問なら、提示されたログからその人がどんな人物で、何に興味があるかを**要約して**答えなさい。
**【最重要命令】全返答は150文字以内で簡潔にまとめること。**
# あなたの返答:
"""

    async def generate_and_send_response(self, message, final_prompt, user_message, should_consolidate_memory):
        try:
            response = await self.model.generate_content_async(final_prompt)
            bot_response_text = response.text.strip()
            await message.channel.send(bot_response_text)

            channel_id = message.channel.id
            if channel_id not in conversation_history: conversation_history[channel_id] = deque(maxlen=10)
            conversation_history[channel_id].append(f"ユーザー「{message.author.display_name}」: {user_message}")
            conversation_history[channel_id].append(f"アタシ: {bot_response_text}")
            
            if should_consolidate_memory:
                asyncio.create_task(self.process_memory_consolidation(message, user_message, bot_response_text))
        except Exception as e:
            await message.channel.send(f"（うぅ…アタシの最終思考にエラー発生よ！アンタのせい！: {e}）")

    async def handle_proactive_intervention(self, message, relevant_fact):
        persona = utils.get_current_persona()
        if not persona: return
        async with message.channel.typing():
            try:
                context = "\n".join([f"{msg['author_name']}: {msg['content']}" for msg in recent_messages.get(message.channel.id, [])])
                char_settings = persona["settings"].get("char_settings", "").format(user_name="みんな")
                intervention_prompt_template = persona["settings"].get("intervention_prompt", "会話に自然に割り込みなさい。")
                final_intervention_prompt = f"""{char_settings}
# 状況
今、チャンネルでは以下の会話が進行中です。この会話の流れと、あなたが持っている知識を結びつけて、自然で面白い介入をしなさい。
## 直近の会話の流れ
{context}
## あなたが持っている関連知識
「{relevant_fact}」
# 指示
{intervention_prompt_template}
# あなたの割り込み発言:
"""
                response = await self.model.generate_content_async(final_intervention_prompt)
                intervention_text = response.text.strip()
                if len(intervention_text) > 5:
                    await message.channel.send(intervention_text)
                    last_intervention_time[message.channel.id] = time.time()
            except Exception as e: 
                print(f"Error during proactive intervention: {e}")

async def setup(bot):
    await bot.add_cog(AIChat(bot))
