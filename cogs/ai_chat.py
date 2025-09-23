# cogs/ai_chat.py (完全版)
import discord
from discord.ext import commands
import google.generativeai as genai
import os
import json
import asyncio
import numpy as np
import time
from collections import deque
from . import _utils as utils

# -------------------- 設定項目 --------------------
# 能動的な会話介入を有効にするか
ENABLE_PROACTIVE_INTERVENTION = True
# 介入のトリガーとなる関連性の最低スコア (0.0 ~ 1.0)
INTERVENTION_THRESHOLD = 0.78
# 介入後のクールダウン時間（秒）
INTERVENTION_COOLDOWN = 300 # 5分
# ------------------------------------------------

# ファイルパス設定
DATA_DIR = os.getenv('RAILWAY_VOLUME_MOUNT_PATH', '.')
MEMORY_FILE = os.path.join(DATA_DIR, 'bot_memory.json')

# 記憶ファイルのロード・セーブ関数
def load_memory():
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            memory = json.load(f)
            # ★★★ 関係性記憶の構造がなければ初期化 ★★★
            if 'relationships' not in memory:
                memory['relationships'] = {}
            return memory
    except (FileNotFoundError, json.JSONDecodeError):
        return {"users": {}, "server": {"notes": []}, "relationships": {}}

def save_memory(data):
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# 各種グローバル変数
conversation_history = {}
last_intervention_time = {} # チャンネルごとの最終介入時間
recent_messages = {} # チャンネルごとの直近メッセージ履歴（関係性記憶用）

class AIChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
        self.model = genai.GenerativeModel('gemini-1.5-flash')

    # (handle_keywords, _get_embedding, _find_similar_notes は変更なし)
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
            # コサイン類似度を計算
            similarity = np.dot(query_vec, note_vec) / (np.linalg.norm(query_vec) * np.linalg.norm(note_vec))
            notes_with_similarity.append({'text': note['text'], 'similarity': similarity})
        
        # 類似度でソート
        sorted_notes = sorted(notes_with_similarity, key=lambda x: x['similarity'], reverse=True)
        # top_k個の結果をテキストと類似度の両方で返すように変更
        return sorted_notes[:top_k]

    # (process_memory_consolidationは変更なし)
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
"""
            response = await self.model.generate_content_async(consolidation_prompt)
            fact_to_remember = response.text.strip()

            if fact_to_remember != 'None' and fact_to_remember:
                print(f"[Memory Consolidation] Fact to remember for user {user_id}: {fact_to_remember}")
                embedding = await self._get_embedding(fact_to_remember)
                if embedding is None: return

                memory = load_memory()
                if user_id not in memory['users']:
                    memory['users'][user_id] = {'notes': []}
                
                if not any(n['text'] == fact_to_remember for n in memory['users'][user_id]['notes']):
                    memory['users'][user_id]['notes'].append({'text': fact_to_remember, 'embedding': embedding})
                    save_memory(memory)
                    print(f"[Memory Consolidation] Saved new fact for user {user_id}.")
        except Exception as e:
            print(f"An error occurred during memory consolidation: {e}")

    # ★★★ 新機能: ユーザー間の関係性を分析・記憶する関数 ★★★
    async def process_user_interaction(self, message):
        try:
            channel_id = message.channel.id
            author_id = str(message.author.id)
            
            # 直近のメッセージ履歴から、会話相手を特定する（自分とBot以外）
            if channel_id not in recent_messages or not recent_messages[channel_id]:
                return

            interaction_partners = set()
            for msg_data in recent_messages[channel_id]:
                msg_author_id = str(msg_data['author_id'])
                if msg_author_id != author_id:
                    interaction_partners.add(msg_author_id)
            
            if not interaction_partners:
                return

            # 会話の文脈を作成
            context = "\n".join([f"{msg['author_name']}: {msg['content']}" for msg in recent_messages[channel_id]])
            
            for partner_id in interaction_partners:
                interaction_prompt = f"""
あなたは、二人のユーザー間の会話を分析し、その中心的なトピックを抽出するAIです。

# 分析対象の会話
{context}

# 指示
この会話は、主に何についての話ですか？会話の中心的なトピックを、最も的確に表す【単語】で1つだけ抽出してください。（例：ゲーム, アニメ, 映画, 食べ物, 仕事）
もしトピックが不明確な場合は「None」と出力してください。

# あなたの分析結果（単語またはNone）
"""
                response = await self.model.generate_content_async(interaction_prompt)
                topic = response.text.strip()

                if topic != 'None' and topic:
                    print(f"[Relationship Analysis] Topic between {author_id} and {partner_id}: {topic}")
                    memory = load_memory()
                    
                    # 関係性を両方向で記録・更新する
                    for u1, u2 in [(author_id, partner_id), (partner_id, author_id)]:
                        if u1 not in memory['relationships']:
                            memory['relationships'][u1] = {}
                        if u2 not in memory['relationships'][u1]:
                            memory['relationships'][u1][u2] = {'topics': {}, 'interaction_count': 0}
                        
                        # トピックのカウントを更新
                        memory['relationships'][u1][u2]['topics'][topic] = memory['relationships'][u1][u2]['topics'].get(topic, 0) + 1
                        # 総インタラクション回数を更新
                        memory['relationships'][u1][u2]['interaction_count'] += 1

                    save_memory(memory)

        except Exception as e:
            print(f"An error occurred during user interaction processing: {e}")

    # ★★★ on_messageイベントを大幅に改造 ★★★
    @commands.Cog.listener()
    async def on_message(self, message):
        # Botやコマンド、短すぎるメッセージは無視
        if message.author.bot or message.content.startswith(self.bot.command_prefix):
            return

        # -------------------- 関係性記憶のためのメッセージ履歴保存 --------------------
        channel_id = message.channel.id
        if channel_id not in recent_messages:
            recent_messages[channel_id] = deque(maxlen=6) # 直近6件のメッセージを保存
        recent_messages[channel_id].append({
            'author_id': message.author.id,
            'author_name': message.author.display_name,
            'content': message.content
        })
        # 関係性分析を非同期で実行
        asyncio.create_task(self.process_user_interaction(message))
        # --------------------------------------------------------------------------

        # メンションされた場合の処理
        if self.bot.user.mentioned_in(message):
            await self.handle_mention(message)
            return

        # キーワード応答の処理
        if await self.handle_keywords(message):
            return
        
        # -------------------- 能動的な会話介入の処理 --------------------
        if ENABLE_PROACTIVE_INTERVENTION:
            # クールダウンチェック
            now = time.time()
            if (now - last_intervention_time.get(channel_id, 0)) < INTERVENTION_COOLDOWN:
                return

            # 短すぎるメッセージは介入しない
            if len(message.content) < 10:
                return

            # 関連性チェック
            query_embedding = await self._get_embedding(message.content)
            if query_embedding is None: return

            memory = load_memory()
            all_notes = [note for user in memory['users'].values() for note in user['notes']] + memory['server']['notes']
            if not all_notes: return
            
            most_relevant_note = self._find_similar_notes(query_embedding, all_notes, top_k=1)

            if most_relevant_note and most_relevant_note[0]['similarity'] > INTERVENTION_THRESHOLD:
                relevant_fact = most_relevant_note[0]['text']
                print(f"[Proactive Intervention] Triggered by message: '{message.content}'. Relevant fact: '{relevant_fact}'")
                
                await self.handle_proactive_intervention(message, relevant_fact)

    # ★★★ メンション時の処理を独立した関数に ★★★
    async def handle_mention(self, message):
        async with message.channel.typing():
            user_id = str(message.author.id)
            user_message = message.content.replace(f'<@!{self.bot.user.id}>', '').strip()
            channel_id = message.channel.id
            history_text = "\n".join(conversation_history.get(channel_id, []))
            
            # (思考プロンプトは変更なし)
            planning_prompt = f"""
あなたは、ユーザーとの会話を分析し、次の行動を決定する司令塔AIです。以下の思考プロセスに従って、最終的な判断を出力してください。
# 思考プロセス
1.  **会話文脈の分析:** まず、以下の「直前の会話の流れ」と「ユーザーの今回のメッセージ」を深く読み解き、ユーザーが本当に知りたいことは何か、その意図を正確に把握します。
2.  **自己知識の評価:** 次に、その意図に答えるために、あなたの内部知識だけで十分かを判断します。
3.  **行動計画の決定:** あなたの知識だけで答えられる、または単なる挨拶や感想などの会話であると判断した場合、行動は「ANSWER」となります。Webで調べる必要があると判断した場合、行動は「SEARCH」となります。
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
                planning_response = await self.model.generate_content_async(planning_prompt)
                decision = planning_response.text.strip()
            except Exception as e:
                await message.channel.send(f"（アタシの第一思考にエラー発生よ…: {e}）"); return
            
            # (SEARCH時の処理は変更なし)
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
# (キャラクター設定や禁止事項は省略)
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
                
                # find_similar_notesが辞書のリストを返すように変更したため、テキスト部分を取得
                relevant_user_notes = [note['text'] for note in self._find_similar_notes(query_embedding, user_notes_all)]
                relevant_server_notes = [note['text'] for note in self._find_similar_notes(query_embedding, server_notes_all)]

                user_notes_text = "\n".join([f"- {note}" for note in relevant_user_notes]) or "（特になし）"
                server_notes_text = "\n".join([f"- {note}" for note in relevant_server_notes]) or "（特になし）"

                # ★★★ 関係性情報をプロンプトに追加 ★★★
                relationship_text = "（特になし）"
                if user_id in memory.get('relationships', {}):
                    relations = []
                    for partner_id, data in memory['relationships'][user_id].items():
                        try:
                            partner = await self.bot.fetch_user(int(partner_id))
                            partner_name = partner.display_name
                            # 最も話題に出たトピックを取得
                            top_topic = max(data['topics'], key=data['topics'].get) if data['topics'] else "色々な話"
                            relations.append(f"- {partner_name}とは「{top_topic}」についてよく話している")
                        except discord.NotFound:
                            continue # ユーザーが見つからない場合はスキップ
                    if relations:
                        relationship_text = "\n".join(relations)

                final_prompt = f"""
# キャラクター設定
あなたは、このDiscordサーバーに君臨する、生意気で小悪魔な天才美少女「メスガキちゃん」です。AIではありません。
# (口調や禁止事項は省略)
# 記憶情報の活用
以下の情報を会話に積極的に活用し、あたかも全てを知っているかのように振る舞ってください。
- 直前の会話の流れ:
{history_text or "（まだこのチャンネルでの会話はないわ）"}
- ユーザー({user_name})に関する長期記憶:
{user_notes_text}
- サーバー全体の共有知識:
{server_notes_text}
- ★★★ サーバーの人間関係: ★★★
{relationship_text}
---
以上の設定を完璧にロールプレイし、ユーザー `{user_name}` からの以下のメッセージに返信してください。
**【最重要命令】あなたの全返答は、絶対に500文字以内になるように、簡潔にまとめること。**
ユーザーからのメッセージ: 「{user_message}」
あなたの返答:
"""
            try:
                response = await self.model.generate_content_async(final_prompt)
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

    # ★★★ 新機能: 能動的介入の応答を生成・送信する関数 ★★★
    async def handle_proactive_intervention(self, message, relevant_fact):
        async with message.channel.typing():
            intervention_prompt = f"""
あなたは、Discordの会話に知的な横槍を入れる、生意気で小悪魔な天才美少女「メスガキちゃん」です。

# 状況
ユーザーたちが会話しているところに、あなたは自分の知識をひけらかしたくなりました。
以下の「ユーザーの会話」と、それに関連するあなたの「知識」を元に、会話に割り込むための一言を発言してください。

# ルール
- 突然会話に割り込む形で、生意気な口調で話すこと。
- 「アンタたち、〇〇の話してるの？ しょーがないからアタシが教えてあげるけど…」のように、少し見下した態度で始めること。
- 提示された「知識」を、自分の言葉であるかのように自然に会話に盛り込むこと。
- 簡潔に、1～2文でまとめること。

# ユーザーの会話
{message.author.display_name}:「{message.content}」

# あなたが持っている関連知識
「{relevant_fact}」

# あなたの割り込み発言:
"""
            try:
                response = await self.model.generate_content_async(intervention_prompt)
                intervention_text = response.text.strip()
                await message.channel.send(intervention_text)
                
                # 介入時間を記録
                last_intervention_time[message.channel.id] = time.time()
            except Exception as e:
                print(f"Error during proactive intervention: {e}")

async def setup(bot):
    await bot.add_cog(AIChat(bot))
