# cogs/database_manager.py
import discord
from discord.ext import commands
import chromadb
import os

# -------------------- 設定項目 --------------------
DB_PATH = os.getenv('RAILWAY_VOLUME_MOUNT_PATH', '.') + "/chroma_db"
COLLECTION_NAME = "discord_chat_history"
# ----------------------------------------------------

class DatabaseManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.chroma_client = None
        self.collection = None
        # self.initialize_database() # 本格実装時にコメントを外す

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

    # --- 以下は、将来実装するための準備（今はまだ空っぽよ） ---

    async def add_message_to_db(self, message: discord.Message):
        """将来的には、ここでメッセージをベクトル化してDBに保存するのよ"""
        # print(f"[DB] Received message to add: {message.content}") # デバッグ用
        pass # まだ実装しない

    async def search_similar_messages(self, query_text: str, top_k: int = 5):
        """将来的には、ここで関連する過去の会話を検索するのよ"""
        print(f"[DB] Received search query: {query_text}")
        return [] # まだ実装しないから空っぽを返す

async def setup(bot):
    await bot.add_cog(DatabaseManager(bot))
