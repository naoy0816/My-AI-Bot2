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
SEARCH_API_KEY = os.getenv('GOOGLE_SEARCH_API_KEY')
SEARCH_ENGINE_ID = os.getenv('GOOGLE_SEARCH_ENGINE_ID')

class AIChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
        self.chat_model = genai.GenerativeModel('gemini-1.5-flash')

    # キーワード応答のロジック
    async def handle_keywords(self, message):
        content = message.content
        # 完全一致じゃなくて、キーワードが含まれてたら反応するようにしたわよ♡
        responses = {
            'おはよう': 'おはよ♡ アンタも朝から元気なワケ？w',
            'おやすみ': 'ふん、せいぜい良い夢でも見なさいよね！ザコちゃん♡',
            'すごい': 'あっはは！当然でしょ？アタシを誰だと思ってんのよ♡',
            '天才': 'あっはは！当然でしょ？アタシを誰だと思ってんのよ♡',
            'ありがとう': 'べ、別にアンタのためにやったんじゃないんだからね！勘違いしないでよね！',
            '感謝': 'べ、別にアンタのためにやったんじゃないんだからね！勘違いしないでよね！',
            '疲れた': 'はぁ？ザコすぎw もっとしっかりしなさいよね！',
            'しんどい': 'はぁ？ザコすぎw もっとしっかりしなさいよね！',
            '好き': 'ふ、ふーん…。まぁ、アンタがアタシの魅力に気づくのは当然だけど？♡',
            'かわいい': 'ふ、ふーん…。まぁ、アンタがアタシの魅力に気づくのは当然だけど？♡',
            'ｗ': '何笑ってんのよ、キモチワルイんだけど？',
            '笑': '何笑ってんのよ、キモチワルイんだけど？',
            'ごめん': 'わかればいいのよ、わかれば。次はないかんね？',
            'すまん': 'わかればいいのよ、わかれば。次はないかんね？',
            '何してる': 'アンタには関係ないでしょ。アタシはアンタと違って忙しいの！',
            'なにしてる': 'アンタには関係ないでしょ。アタシはアンタと違って忙しいの！',
            'お腹すいた': '自分でなんとかしなさいよね！アタシはアンタのママじゃないんだけど？',
            'はらへった': '自分でなんとかしなさいよね！アタシはアンタのママじゃないんだけど？',
        }
        for keyword, response in responses.items():
            if keyword in content:
                await message.channel.send(response)
                return True # 応答した
        return False # 応答しなかった

    async def _get_embedding(self, text):
        try:
            result = await genai.embed_content_async(model="models/text-embedding-004", content=text, task_type="RETRIEVAL_DOCUMENT")
            return result['embedding']
        except Exception as e:
            print(f"Embedding error: {e}")
            return None

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
        # ... (この部分は現状維持でOK) ...
        pass

    def google_search(self, query):
        # ... (この部分は現状維持でOK) ...
        pass
        
    @commands.Cog.listener()
    async def on_message(self, message):
        # 自分自身のメッセージは無視
        if message.author == self.bot.user:
            return

        # メンションされたらAIチャットを起動
        if self.bot.user.mentioned_in(message):
            # (AIチャットのメインロジック部分は変更なし)
            # ...
            # AIが応答したら、他の処理（キーワードやコマンド）はしないのでここで終わり
            return

        # コマンドでもメンションでもない平文の場合、キーワード応答を試す
        if not message.content.startswith(self.bot.command_prefix):
            responded = await self.handle_keywords(message)
            if responded:
                # キーワードで応答したら、コマンド処理はしないのでここで終わり
                return

        # 上のいずれにも当てはまらない場合（つまり、コマンドの可能性があるメッセージ）、
        # ボットにコマンドとして処理させる
        await self.bot.process_commands(message)


async def setup(bot):
    await bot.add_cog(AIChat(bot))
