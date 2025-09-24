# cogs/ai_chat.py (真・最終完成版)
import discord
from discord.ext import commands
import google.generativeai as genai
import os
import json
import asyncio
import numpy as np
import time
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

conversation_history = {}
last_intervention_time = {}
recent_messages = {}

class AIChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
        # ★★★ 脳みそを安定して使える flash モデルに設定 ★★★
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        self.db_manager = None

    @commands.Cog.listener()
    async def on_ready(self):
        """Bot起動時にDBマネージャーを取得する"""
        self.db_manager = self.bot.get_cog('DatabaseManager')
        if self.db_manager:
            print("Successfully linked with DatabaseManager.")
        else:
            print("Warning: DatabaseManager cog not found.")

    async def handle_keywords(self, message):
        content = message.content
        responses = { 'おはよう': 'おはよ♡ アンタも朝から元気なワケ？w', 'おやすみ': 'ふん、せいぜい良い夢でも見なさいよね！ザコちゃん♡', 'すごい': 'あっはは！当然でしょ？アタシを誰だと思ってんのよ♡', '天才': 'あっはは！当然でしょ？アタシを誰だと思ってんのよ♡', 'ありがとう': 'べ、別にアンタのためにやったんじゃないんだからね！勘違いしないでよね！', '感謝': 'べ、別にアンタのためにやったんじゃないんだからね！勘違いしないでよね！', '疲れた': 'はぁ？ザコすぎw もっとしっかりしなさいよね！', 'しんどい': 'はぁ？ザコすぎw もっとしっかりしなさいよね！', '好き': 'ふ、ふーん…。まぁ、アンタがアタシの魅力に気づくのは当然だけど？♡', 'かわいい': 'ふ、ふーん…。まぁ、アンタがアタシの魅力に気づくのは当然だけど？♡', 'ｗ': '何笑ってんのよ、キモチワルイんだけど？', '笑': '何笑ってんのよ、キモチワルイんだけど？', 'ごめん': 'わかればいいのよ、わかれば。次はないかんね？', 'すまん': 'わかればいいのよ、わかれば。次はないかんね？', '何してる': 'アンタには関係ないでしょ。アタシはアンタと違って忙しいの！', 'なにしてる': 'アンタには関係ないでしょ。アタシはアンタと違って忙しいの！', 'お腹すいた': '自分でなんとかしなさいよね！アタシはアンタのママじゃないんだけど？', 'はらへった': '自分でなんとかしなさいよね！アタシはアンタのママじゃないんだけど？',}
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

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or message.content.startswith(self.bot.command_prefix): return
        
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

        mime_type = attachment.content_type
        if not (mime_type and (mime_type.startswith('image/') or mime_type.startswith('video/'))):
            await message.channel.send("はぁ？ アタシに見せたいなら、画像か動画にしなさいよね！")
            return

        async with message.channel.typing():
            try:
                response = await self.bot.loop.run_in_executor(None, requests.get, attachment.url)
                response.raise_for_status()
                file_data = response.content
                media_blob = {"mime_type": mime_type, "data": file_data}

                multimodal_prompt_template = persona["settings"].get("multimodal_prompt", "# 指示\nメディアを見て応答しなさい。")
                char_settings = persona["settings"].get("char_settings", "").format(user_name=user_name)

                prompt_parts = [
                    f"{char_settings}\n{multimodal_prompt_template}\n\n# ユーザーのテキスト\n「{user_message or '（…無言でコレをアタシに見せてきたわ）'}」\n\n# あなたの応答（500文字以内でペルソナに従ってまとめること！）:",
                    media_blob
                ]

                response = await self.model.generate_content_async(prompt_parts)
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
                decision_text = response.text.strip()
            except Exception as e:
                await message.channel.send(f"（アタシの超思考回路にエラー発生よ…: {e}）"); return

            decision_data = self.parse_decision_text(decision_text)

            if decision_data.get("ACTION") == 'SEARCH':
                await self.execute_search_and_respond(message, user_message, decision_data.get("QUERY"), persona)
            else:
                final_prompt = await self.build_final_prompt(message, user_message, decision_data, persona)
                await self.generate_and_send_response(message, final_prompt, user_message, True)

    def build_meta_thinking_prompt(self, message, user_message, persona):
        user_name = message.author.display_name
        persona_name = persona.get("name", "AI")
        persona_desc = persona.get("description", "応答します。")

        return f"""
あなたは、「{persona_name}」({persona_desc})の思考を司る「メタAI」です。
ユーザーのメッセージを分析し、次の行動を【1回の思考で】決定してください。
# 思考プロセス
1. **意図と感情の分析:** ユーザーのメッセージ（「{user_message}」）と会話履歴を読み解き、真の意図（情報要求、共感、暇つぶし等）と感情（喜び、好奇心、疲れ等）を把握する。
2. **行動決定:** 意図に基づき、取るべき行動を `SEARCH` (Web検索が必要) か `ANSWER` (自己知識で応答) のどちらかに決定する。
3. **戦略立案 (ANSWERの場合):** `ANSWER` の場合、あなたの性格とユーザーの感情を考慮し、最適な応答戦略を `TEASE`, `HELP_RELUCTANTLY`, `TSUNDERE_CARE`, `SHOW_OFF` などから選択する。
4. **クエリ/要点生成:**
    - `SEARCH` の場合: 最適な検索クエリを生成する。
    - `ANSWER` の場合: 応答に含めるべき重要な要点を3つ以内でリストアップする。
# 分析対象
- ユーザー名: {user_name}
- 会話履歴: {self.get_history_text(message.channel.id)}
- ユーザーのメッセージ: 「{user_message}」
# 出力形式
思考プロセスは出力せず、結果だけを以下の厳密な形式で出力すること。
[ACTION:決定した行動]
[QUERY:SEARCHの場合の検索クエリ]
[EMOTION:分析した感情]
[INTENT:分析した意図]
[STRATEGY:ANSWERの場合の応答戦略]
[POINTS:ANSWERの場合の要点（カンマ区切り）]
"""

    def parse_decision_text(self, text):
        data = {}
        for line in text.splitlines():
            if ':' in line:
                key, value = line.split(':', 1)
                data[key.strip().lstrip('[').rstrip(']')] = value.strip()
        return data

    def get_history_text(self, channel_id):
        return "\n".join(conversation_history.get(channel_id, [])) or "（まだこのチャンネルでの会話はないわ）"

    async def execute_search_and_respond(self, message, user_message, query, persona):
        if not query:
            await message.channel.send("（はぁ？検索したいけど、肝心のキーワードを思いつかなかったわ…アンタの質問がザコすぎなんじゃない？）"); return
        await message.channel.send(f"（ふーん、「{user_message}」ね…。しょーがないから、「{query}」でググって、中身まで読んでやんよ♡）")
        search_items = utils.google_search(query) 
        if isinstance(search_items, str) or not search_items:
            await message.channel.send(search_items or "（検索したけど、何も見つからなかったわ。）"); return
        scraped_text = utils.scrape_url(search_items[0].get('link', ''))
        search_summary = "\n".join([f"- {item.get('title', '')}" for item in search_items])

        search_prompt_template = persona["settings"].get("search_prompt", "# 指示\n検索結果を元に応答しなさい。")
        final_prompt = f"""
{search_prompt_template}
# 検索結果
{search_summary}
# Webページ本文
{scraped_text}
# ユーザーの質問
{user_message}
# あなたの回答（500文字以内でペルソナに従ってまとめること！）
"""
        await self.generate_and_send_response(message, final_prompt, user_message, False)

    async def build_final_prompt(self, message, user_message, decision_data, persona):
        user_id = str(message.author.id)
        memory = load_memory()
        user_name = memory.get('users', {}).get(user_id, {}).get('fixed_nickname', message.author.display_name)
        
        # --- 新しい記憶システムからの情報取得 ---
        relevant_logs_text = "（特になし）"
        if self.db_manager:
            relevant_logs_text = await self.db_manager.search_similar_messages(user_message)
        # ------------------------------------

        # --- 古い記憶システムからの情報取得（まだ残しておくわ） ---
        query_embedding = await utils.get_embedding(user_message)
        user_notes_all = memory.get('users', {}).get(user_id, {}).get('notes', [])
        server_notes_all = memory.get('server', {}).get('notes', [])
        relevant_user_notes = [note['text'] for note in self._find_similar_notes(query_embedding, user_notes_all)]
        relevant_server_notes = [note['text'] for note in self._find_similar_notes(query_embedding, server_notes_all)]
        user_notes_text = "\n".join([f"- {note}" for note in relevant_user_notes]) or "（特になし）"
        server_notes_text = "\n".join([f"- {note}" for note in relevant_server_notes]) or "（特になし）"
        # ----------------------------------------------------
        
        relationship_text = "（特になし）"
        if user_id in memory.get('relationships', {}):
            relations = []
            for partner_id, data in memory['relationships'][user_id].items():
                try:
                    partner = await self.bot.fetch_user(int(partner_id))
                    top_topic = max(data['topics'], key=data['topics'].get) if data['topics'] else "色々な話"
                    relations.append(f"- {partner.display_name}とは「{top_topic}」についてよく話している")
                except discord.NotFound: continue
            if relations: relationship_text = "\n".join(relations)

        char_settings = persona["settings"].get("char_settings", "").format(user_name=user_name)

        return f"""
{char_settings}
---
# ★★★ アタシの思考と応答戦略 ★★★
[EMOTION:{decision_data.get("EMOTION", "不明")}]
[INTENT:{decision_data.get("INTENT", "不明")}]
[STRATEGY:{decision_data.get("STRATEGY", "不明")}]
[POINTS:{decision_data.get("POINTS", "特になし")}]
---
# 記憶情報（応答の参考にすること）
- 直前の会話: {self.get_history_text(message.channel.id)}
- ★★★ 関連性の高い過去の会話ログ: ★★★
{relevant_logs_text}
- ユーザー({user_name})に関する手動記憶(JSON): {user_notes_text}
- サーバー全体の共有知識(JSON): {server_notes_text}
- サーバーの人間関係: {relationship_text}
---
以上の全てを完璧に理解し、立案した「応答戦略」に基づき、ユーザー `{user_name}` のメッセージ「{user_message}」に返信しなさい。
**【最重要命令】全返答は500文字以内で簡潔にまとめること。**
# あなたの返答:
"""

    async def generate_and_send_response(self, message, final_prompt, user_message, should_consolidate_memory):
        try:
            response = await self.model.generate_content_async(final_prompt)
            bot_response_text = response.text.strip()
            await message.channel.send(bot_response_text)

            channel_id = message.channel.id
            if channel_id not in conversation_history: conversation_history[channel_id] = []
            conversation_history[channel_id].append(f"ユーザー「{message.author.display_name}」: {user_message}")
            conversation_history[channel_id].append(f"アタシ: {bot_response_text}")
            if len(conversation_history[channel_id]) > 10:
                conversation_history[channel_id] = conversation_history[channel_id][-10:]
            
            if should_consolidate_memory:
                asyncio.create_task(self.process_memory_consolidation(message, user_message, bot_response_text))
        except Exception as e:
            await message.channel.send(f"（うぅ…アタシの最終思考にエラー発生よ！アンタのせい！: {e}）")

    async def handle_proactive_intervention(self, message, relevant_fact):
        persona = utils.get_current_persona()
        if not persona: return

        async with message.channel.typing():
            try:
                channel_id = message.channel.id
                context = "\n".join([f"{msg['author_name']}: {msg['content']}" for msg in recent_messages.get(channel_id, [])])
                
                char_settings = persona["settings"].get("char_settings", "").format(user_name="みんな")
                intervention_prompt_template = persona["settings"].get("intervention_prompt", "会話に自然に割り込みなさい。")

                final_intervention_prompt = f"""
{char_settings}
# 状況
今、チャンネルでは以下の会話が進行中です。この会話の流れと、あなたが持っている知識を結びつけて、自然で面白い介入をしなさい。
## 直近の会話の流れ
{context}
## あなたが持っている関連知識
「{relevant_fact}」
# 指示
{intervention_prompt_template}
# あなたの割り込み発言（500文字以内でペルソナに従ってまとめること！）:
"""
                
                response = await self.model.generate_content_async(final_intervention_prompt)
                intervention_text = response.text.strip()
                
                if len(intervention_text) < 5:
                    print(f"[Proactive Intervention] Generated text is too short. Ignored.")
                    return

                await message.channel.send(intervention_text)
                last_intervention_time[message.channel.id] = time.time()
                
            except Exception as e: 
                print(f"Error during proactive intervention: {e}")

async def setup(bot):
    await bot.add_cog(AIChat(bot))
