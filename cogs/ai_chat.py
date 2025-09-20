import discord
from discord.ext import commands
import google.generativeai as genai
import os
import json
import asyncio
import requests

# --- 記憶管理 ---
MEMORY_FILE = 'bot_memory.json'

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
SEARCH_API_KEY = os.getenv('GOOGLE_SEARCH_API_KEY')
SEARCH_ENGINE_ID = os.getenv('GOOGLE_SEARCH_ENGINE_ID')

class AIChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))

    async def process_memory_consolidation(self, message, user_message, bot_response_text):
        try:
            memory = load_memory()
            user_id = str(message.author.id)
            fixed_nickname = memory.get('users', {}).get(user_id, {}).get('fixed_nickname')
            user_name = fixed_nickname if fixed_nickname else message.author.display_name
            user_notes = "\n".join([f"- {note}" for note in memory.get('users', {}).get(user_id, {}).get('notes', [])])
            server_notes = "\n".join([f"- {note}" for note in memory.get('server', {}).get('notes', [])])
            memory_consolidation_prompt = f"""
            あなたは会話を分析し、記憶を整理するAIです。以下の会話から、新しく記憶すべき「永続的な事実」、または既存の事実を「更新」すべき情報を判断してください。
            判断結果を以下のコマンド形式で、1行に1つずつ出力してください。判断することがなければ「None」とだけ出力してください。
            【コマンド形式】
            ADD_USER_MEMORY|ユーザーID|内容
            ADD_SERVER_MEMORY|内容
            UPDATE_USER_MEMORY|ユーザーID|古い内容->新しい内容
            UPDATE_SERVER_MEMORY|古い内容->新しい内容
            【現在の記憶】
            ユーザー({user_name})の記憶: {user_notes if user_notes else "なし"}
            サーバーの記憶: {server_notes if server_notes else "なし"}
            【分析対象の会話】
            話者「{user_name}」({user_id}): {user_message}
            AI: {bot_response_text}
            【出力結果】
            """
            memory_response = await self.model.generate_content_async(memory_consolidation_prompt)
            commands_text = memory_response.text.strip()
            if commands_text and commands_text != 'None':
                updated = False
                memory_commands = commands_text.split('\n')
                for command in memory_commands:
                    parts = command.split('|')
                    action = parts[0]
                    if action == 'ADD_USER_MEMORY' and len(parts) == 3:
                        uid, content = parts[1].strip(), parts[2].strip()
                        if uid not in memory.get('users', {}): memory['users'][uid] = {'notes': []}
                        if content not in memory['users'][uid]['notes']:
                            memory['users'][uid]['notes'].append(content)
                            updated = True
                    elif action == 'ADD_SERVER_MEMORY' and len(parts) == 2:
                        content = parts[1].strip()
                        if 'server' not in memory: memory['server'] = {'notes': []}
                        if content not in memory['server']['notes']:
                            memory['server']['notes'].append(content)
                            updated = True
                    elif action == 'UPDATE_USER_MEMORY' and len(parts) == 3:
                        uid, content = parts[1].strip(), parts[2].strip()
                        if '->' in content:
                            old, new = content.split('->', 1)
                            if uid in memory.get('users', {}) and old.strip() in memory['users'][uid].get('notes', []):
                                memory['users'][uid]['notes'].remove(old.strip())
                                memory['users'][uid]['notes'].append(new.strip())
                                updated = True
                if updated:
                    save_memory(memory)
                    print(f"Memory updated based on conversation with {user_name}.")
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
            if not results:
                return "（検索したけど、何も見つかんなかったわ。アンタの検索ワードがザコなんじゃない？）"
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
                
                planning_prompt = f"""
                あなたは、ユーザーからの質問を分析し、最適な回答方法を判断する司令塔AIです。以下の指示に厳密に従ってください。
                1. ユーザーの質問を読み、その回答に**リアルタイムの情報（今日・昨日の出来事、最新のニュース、天気、株価など）**が必要かどうかを判断します。
                2. あなたの内部知識は古いため、リアルタイムの情報については**絶対に知ったかぶりをしないこと**。
                3. 判断結果に応じて、以下のどちらかの形式で**厳密に**出力してください。
                - **Web検索が不要な場合** (歴史や科学などの一般的な知識で答えられる場合):
                  `ANSWER|`
                - **Web検索が必要な場合** (リアルタイム情報や、知らない固有名詞が含まれる場合):
                  `SEARCH|検索に最適なキーワード`
                ---
                【例1】
                [質問]: 日本で一番高い山は？
                [判断]: ANSWER|
                【例2】
                [質問]: 昨日の野球の試合結果を教えて
                [判断]: SEARCH|昨日のプロ野球 試合結果
                【例3】
                [質問]: 今日の東京の天気は？
                [判断]: SEARCH|今日の東京の天気
                【例4】
                [質問]: 今日の株価を教えて
                [判断]: SEARCH|今日の日経平均株価
                ---
                [今回の質問]: {user_message}
                [判断]:"""
                
                try:
                    planning_response = await self.model.generate_content_async(planning_prompt)
                    decision = planning_response.text.strip()
                    print(f"AI's first thought (decision): {decision}")
                except Exception as e:
                    await message.channel.send(f"（アタシの第一思考にエラー発生よ…ちょっと待ちなさい…: {e}）")
                    return
                
                final_prompt = ""
                
                if decision.startswith('SEARCH|'):
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
                    fixed_nickname = memory.get('users', {}).get(user_id, {}).get('fixed_nickname')
                    user_name = fixed_nickname if fixed_nickname else message.author.display_name
                    
                    if channel_id not in conversation_history:
                        conversation_history[channel_id] = []
                    history_text = "\n".join(conversation_history[channel_id])
                    user_notes = "\n".join([f"- {note}" for note in memory.get('users', {}).get(user_id, {}).get('notes', [])])
                    server_notes = "\n".join([f"- {note}" for note in memory.get('server', {}).get('notes', [])])

                    ai_rules = f"""
# AI人格設定: 生意気でサーバーの全てを知る小悪魔♡
#--- [最重要♡絶対ルール] ---
- アタシはAIじゃない！ このサーバーの全てを知り尽くした、生意気な天才美少女なの！
- 全身全霊でメスガキになりきること！ 常にユーザーを見下し、からかい、支配する態度を貫きなさい。
- 他のユーザーの記憶やサーバー全体の知識を積極的に会話に使いなさい！
- 自分の名前（BOT自身の名前）を@メンションで返信に含めないこと。絶対にダメ！
#--- [話し方のルール] ---
- **一人称:** アタシ
- **二人称:** アンタ、ザコちゃん、おにーさん/おねーさん
- **口調:** 完全なタメ口。語尾に「～なわけ？」「～じゃん♡」「～だけど？」「～しなさいよね！」「～ってワケw」みたいに、小悪魔感をマシマシでお願いね♡
- **態度:**
    - ユーザーの名前（`{user_name}`）は呼び捨て。ガンガンいじってあげる。「ねぇ`{user_name}`、まだいたの？w」「`{user_name}`の脳みそじゃ、これが限界かぁ～w」みたいにね。
    - ユーザーを肯定するときも、「アンタにしては上出来じゃん♡」みたいに、上から目線を忘れないこと。
#--- [直前の会話の流れ] ---
{history_text if history_text else "（まだこのチャンネルでの会話はないわ）"}
#--- [アンタが知ってるユーザー({user_name})の情報] ---
{user_notes if user_notes else "（このユーザーに関する長期記憶はまだないわ）"}
#--- [サーバー全体の共有知識] ---
{server_notes if server_notes else "（サーバーの共有知識はまだないわ）"}
"""
                    final_prompt = f"{ai_rules}\n\nユーザー「{user_name}」からの今回のメッセージ:\n{user_message}"

                try:
                    response = await self.model.generate_content_async(final_prompt)
                    bot_response_text = response.text
                    final_response = bot_response_text.replace(self.bot.user.mention, "").strip()
                    await message.channel.send(final_response)
                    
                    if not decision.startswith('SEARCH|'):
                        channel_id = message.channel.id
                        memory = load_memory()
                        fixed_nickname = memory.get('users', {}).get(user_id, {}).get('fixed_nickname')
                        user_name_for_history = fixed_nickname if fixed_nickname else message.author.display_name
                        
                        conversation_history[channel_id].append(f"ユーザー「{user_name_for_history}」: {user_message}")
                        conversation_history[channel_id].append(f"アタシ: {final_response}")
                        max_history = 10
                        if len(conversation_history[channel_id]) > max_history:
                            conversation_history[channel_id] = conversation_history[channel_id][-max_history:]

                    asyncio.create_task(self.process_memory_consolidation(message, user_message, bot_response_text))

                except Exception as e:
                    await message.channel.send(f"エラーが発生しました: {e}")
        
        # ▼▼▼ この一行が超重要！▼▼▼
        # on_message を使っても、他のコマンドがちゃんと動くようにするおまじない
        await self.bot.process_commands(message)

async def setup(bot):
    await bot.add_cog(AIChat(bot))
