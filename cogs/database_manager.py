# cogs/database_manager.py (最終版)
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
            existing = self.collection.get(ids=[str(message.id)])
            if existing and existing['ids']:
                return False
            embedding = await utils.get_embedding(message.content)
            if not embedding:
                return False
            metadata = {
                "author_id": str(message.author.id),
                "author_name": message.author.name,
                "channel_id": str(message.channel.id),
                "channel_name": message.channel.name,
                "timestamp": message.created_at.isoformat()
            }
            self.collection.add(
                embeddings=[embedding],
                documents=[message.content],
                metadatas=[metadata],
                ids=[str(message.id)]
            )
            return True
        except Exception as e:
            print(f"Error adding message {message.id} to DB: {e}")
            return False

    # ★★★ ここが「神の記憶」を呼び覚ます検索機能よ！ ★★★
    async def search_similar_messages(self, query_text: str, top_k: int = 5):
        """関連する過去の会話をベクトル検索して、プロンプト用のテキストを返す"""
        if not self.collection or not query_text:
            return "（関連する過去ログは見つからなかったわ）"

        try:
            # 検索用の文章をベクトル化
            query_embedding = await utils.get_embedding(query_text, task_type="RETRIEVAL_QUERY")
            if not query_embedding:
                return "（関連する過去ログは見つからなかったわ）"

            # DBに問い合わせ
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k
            )
            
            if not results or not results['documents'][0]:
                return "（関連する過去ログは見つからなかったわ）"

            # プロンプトに埋め込むためのテキストを整形
            found_logs = []
            for i, doc in enumerate(results['documents'][0]):
                metadata = results['metadatas'][0][i]
                author = metadata.get('author_name', '不明')
                timestamp = metadata.get('timestamp', '過去').split('T')[0]
                log_entry = f"- {timestamp}, {author}「{doc}」"
                found_logs.append(log_entry)
            
            return "\n".join(found_logs)

        except Exception as e:
            print(f"Error searching similar messages: {e}")
            return f"（過去ログ検索中にエラー発生: {e}）"

async def setup(bot):
    await bot.add_cog(DatabaseManager(bot))
