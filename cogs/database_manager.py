# cogs/database_manager.py (最終完成版)
import discord
from discord.ext import commands
import chromadb
from chromadb.config import Settings
import os
from . import _utils as utils
import traceback

# -------------------- 設定項目 --------------------
DB_PATH = os.getenv('RAILWAY_VOLUME_MOUNT_PATH', '.') + "/chroma_db"
COLLECTION_NAME_PREFIX = "channel_history_"
# ★★★ 検索結果の足切りスコア。この数字より距離が遠いものは無視する (小さいほど厳しい) ★★★
DISTANCE_THRESHOLD = 1.0
# ----------------------------------------------------

class DatabaseManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.chroma_client = None
        self.initialize_database()

    def initialize_database(self):
        """データベースクライアントを初期化する"""
        print("Initializing ChromaDB Client...")
        try:
            self.chroma_client = chromadb.PersistentClient(
                path=DB_PATH,
                settings=Settings(anonymized_telemetry=False)
            )
            print("ChromaDB Client initialized.")
        except Exception as e:
            print(f"FATAL: Failed to initialize ChromaDB Client: {e}")

    def get_channel_collection(self, channel_id: str):
        if not self.chroma_client:
            return None
        collection_name = f"{COLLECTION_NAME_PREFIX}{channel_id}"
        return self.chroma_client.get_or_create_collection(name=collection_name)

    def reset_all_collections(self):
        """DB内の全ての会話履歴コレクションを削除して再生成する"""
        if not self.chroma_client:
            raise Exception("ChromaDB client is not initialized.")
        collections = self.chroma_client.list_collections()
        deleted_count = 0
        for collection in collections:
            if collection.name.startswith(COLLECTION_NAME_PREFIX):
                self.chroma_client.delete_collection(name=collection.name)
                deleted_count += 1
        self.initialize_database()
        return deleted_count

    async def add_message_to_db(self, message: discord.Message):
        """メッセージを、そのチャンネル専用の書庫に保存する"""
        collection = self.get_channel_collection(str(message.channel.id))
        if not collection or not message.content or len(message.content) < 5:
            return False
        try:
            existing = collection.get(ids=[str(message.id)])
            if existing and existing['ids']:
                return False
            embedding = await utils.get_embedding(message.content)
            if not embedding:
                return False
            metadata = {
                "author_id": str(message.author.id),
                "author_name": message.author.name,
                "timestamp": message.created_at.isoformat()
            }
            collection.add(
                embeddings=[embedding],
                documents=[message.content],
                metadatas=[metadata],
                ids=[str(message.id)]
            )
            return True
        except Exception as e:
            print(f"Error adding message {message.id} to DB collection for channel {message.channel.id}: {e}")
            return False

    # ★★★ ここが「神の記憶」を呼び覚ます検索機能の【最終完成版】よ！ ★★★
    async def search_similar_messages(self, query_text: str, channel_id: str, author_id: str = None, top_k: int = 5):
        """【チャンネルとユーザーを指定して】関連する過去の会話をベクトル検索する"""
        collection = self.get_channel_collection(channel_id)
        if not collection or not query_text:
            return "（関連する過去ログは見つからなかったわ）"

        try:
            collection_count = collection.count()
            if collection_count == 0:
                return "（このチャンネルには、まだ何も記憶がないわ…）"

            query_embedding = await utils.get_embedding(query_text, task_type="RETRIEVAL_QUERY")
            if not query_embedding:
                return "（クエリのベクトル化に失敗して、検索できなかったわ）"

            where_filter = {}
            if author_id:
                where_filter = {"author_id": author_id}

            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k * 2, collection_count), # 足切りされる可能性があるので、少し多めに取得
                where=where_filter if where_filter else None,
                include=["metadatas", "documents", "distances"] # ★★★ 距離スコアも取得 ★★★
            )
            
            if not results or not results.get('documents') or not results['documents'][0]:
                return "（このチャンネルには、関連する過去ログはないみたい…）"

            found_logs = []
            print(f"--- [DB RECALL DEBUG] Query: '{query_text}' ---")
            for i, doc in enumerate(results['documents'][0]):
                distance = results['distances'][0][i]
                
                # ★★★ ここで足切り！ ★★★
                if distance > DISTANCE_THRESHOLD:
                    print(f"  -> REJECTED (distance: {distance:.4f} > {DISTANCE_THRESHOLD}): 「{doc[:30]}...」")
                    continue
                
                print(f"  -> ACCEPTED (distance: {distance:.4f} <= {DISTANCE_THRESHOLD}): 「{doc[:30]}...」")
                
                metadata = results['metadatas'][0][i]
                author = metadata.get('author_name', '不明')
                timestamp = metadata.get('timestamp', '過去').split('T')[0]
                log_entry = f"- {timestamp}, {author}「{doc}」"
                found_logs.append(log_entry)
                
                # 上位5件が見つかったら終了
                if len(found_logs) >= top_k:
                    break
            
            print("---------------------------------")
            
            if not found_logs:
                return "（関連性の高い過去ログは見つからなかったわ…）"

            return "\n".join(found_logs)
        except Exception as e:
            print(f"FATAL Error during search_similar_messages in channel {channel_id}: {e}")
            traceback.print_exc()
            return f"（過去ログ検索中に致命的なエラーが発生したわ: {e}）"

async def setup(bot):
    await bot.add_cog(DatabaseManager(bot))
