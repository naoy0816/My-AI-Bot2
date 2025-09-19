import discord
from discord.ext import commands
import google.generativeai as genai
import os
import json
import asyncio

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

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user or message.content.startswith('!'):
            return
        if self.bot.user.mentioned_in(message):
            async with message.channel.typing():
                memory = load_memory()
                user_id = str(message.author.id)
                channel_id = message.channel.id
                fixed_nickname = memory.get('users', {}).get(user_id, {}).get('fixed_nickname')
                user_name = fixed_nickname if fixed_nickname else message.author.display_name
                user_message = message.content.replace(f'<@!{self.bot.user.id}>', '').strip()
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
#--- [サーバー全体の共有知識（他のユーザーの情報も含む）] ---
{server_notes if server_notes else "（サーバーの共有知識はまだないわ）"}
"""
                prompt = f"{ai_rules}\n\nユーザー「{user_name}」からの今回のメッセージ:\n{user_message}"
                try:
                    response = await self.model.generate_content_async(prompt)
                    bot_response_text = response.text
                    final_response = bot_response_text.replace(self.bot.user.mention, "").strip()
                    await message.channel.send(final_response)
                    conversation_history[channel_id].append(f"ユーザー「{user_name}」: {user_message}")
                    conversation_history[channel_id].append(f"アタシ: {final_response}")
                    max_history = 10
                    if len(conversation_history[channel_id]) > max_history:
                        conversation_history[channel_id] = conversation_history[channel_id][-max_history:]
                    asyncio.create_task(self.process_memory_consolidation(message, user_message, bot_response_text))
                except Exception as e:
                    await message.channel.send(f"エラーが発生しました: {e}")

async def setup(bot):
    await bot.add_cog(AIChat(bot))