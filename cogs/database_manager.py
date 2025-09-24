# cogs/database_manager.py (完全版)
import discord
from discord.ext import commands
import chromadb
import os
from . import _utils as utils

# -------------------- 設定項目 --------------------
DB_PATH = os.getenv('RAILWAY_VOLUME_MOUNT_PATH', '.') + "/chroma_db"
COLLECTION_NAME = "discord_chat_history"
# ----------------------------------------------------

class DatabaseManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.chroma_client = None
        self.collection = None
        self.initialize_database()

    def initialize_database(self):
        """データベースを初期化して、コレクションを準備する"""
        print("Initializing ChromaDB...")
        try:
            self.chroma_client = chromadb.PersistentClient(path=DB_PATH)
            self.collection = self.chroma_client.get_or_create_collection(name=COLLECTION_NAME)
            print(f"ChromaDB initialized. Collection '{COLLECTION_NAME}' is ready.")
            print(f"Total documents in collection: {self.collection.count()}")
        except Exception as e:
            print(f"FATAL: Failed to initialize ChromaDB: {e}")

    async def add_message_to_db(self, message: discord.Message):
        """メッセージをベクトル化してDBに保存する。重複はスキップ。"""
        if not self.collection or not message.content or len(message.content) < 5:
            return False

        try:
            # 1. 重複チェック
            existing = self.collection.get(ids=[str(message.id)])
            if existing and existing['ids']:
                return False

            # 2. ベクトル化
            embedding = await utils.get_embedding(message.content)
            if not embedding:
                return False

            # 3. メタデータ作成
            metadata = {
                "author_id": str(message.author.id),
                "author_name": message.author.name,
                "channel_id": str(message.channel.id),
                "channel_name": message.channel.name,
                "timestamp": message.created_at.isoformat()
            }

            # 4. DBに追加
            self.collection.add(
                embeddings=[embedding],
                documents=[message.content],
                metadatas=[metadata],
                ids=[str(message.id)]
            )
            return True # 追加に成功
        except Exception as e:
            print(f"Error adding message {message.id} to DB: {e}")
            return False # 追加に失敗

    async def search_similar_messages(self, query_text: str, top_k: int = 5):
        """関連する過去の会話を検索する (将来のための準備)"""
        print(f"[DB] Received search query: {query_text}")
        # (将来、ここにベクトル検索のロジックを実装する)
        return []

async def setup(bot):
    await bot.add_cog(DatabaseManager(bot))
