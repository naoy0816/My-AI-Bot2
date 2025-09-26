# cogs/database_manager.py (横断検索機能搭載版)
import discord
from discord.ext import commands
import chromadb
from chromadb.config import Settings
import os
from . import _utils as utils
import traceback
import itertools

# -------------------- 設定項目 --------------------
DB_PATH = os.getenv('RAILWAY_VOLUME_MOUNT_PATH', '.') + "/chroma_db"
COLLECTION_NAME_PREFIX = "channel_history_"
DISTANCE_THRESHOLD = 0.8
# ----------------------------------------------------

class DatabaseManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.chroma_client = None
        self.initialize_database()

    def initialize_database(self):
        print("Initializing ChromaDB Client...")
        try:
            self.chroma_client = chromadb.PersistentClient(path=DB_PATH, settings=Settings(anonymized_telemetry=False))
            print("ChromaDB Client initialized.")
        except Exception as e:
            print(f"FATAL: Failed to initialize ChromaDB Client: {e}")

    def get_channel_collection(self, channel_id: str):
        if not self.chroma_client: return None
        collection_name = f"{COLLECTION_NAME_PREFIX}{channel_id}"
        return self.chroma_client.get_or_create_collection(name=collection_name)

    def reset_all_collections(self):
        if not self.chroma_client: raise Exception("ChromaDB client is not initialized.")
        collections = self.chroma_client.list_collections()
        deleted_count = 0
        for collection in collections:
            if collection.name.startswith(COLLECTION_NAME_PREFIX):
                self.chroma_client.delete_collection(name=collection.name)
                deleted_count += 1
        self.initialize_database()
        return deleted_count

    async def add_message_to_db(self, message: discord.Message):
        collection = self.get_channel_collection(str(message.channel.id))
        if not collection or not message.content or len(message.content) < 5: return False
        try:
            if collection.get(ids=[str(message.id)])['ids']: return False
            embedding = await utils.get_embedding(message.content)
            if not embedding: return False
            metadata = {"author_id": str(message.author.id), "author_name": message.author.name, "timestamp": message.created_at.isoformat()}
            collection.add(embeddings=[embedding], documents=[message.content], metadatas=[metadata], ids=[str(message.id)])
            return True
        except Exception as e:
            print(f"Error adding message {message.id} to DB collection for channel {message.channel.id}: {e}")
            return False

    async def search_similar_messages(self, query_text: str, channel_id: str, author_id: str = None, top_k: int = 5):
        collection = self.get_channel_collection(channel_id)
        if not collection or not query_text: return "（関連する過去ログは見つからなかったわ）"
        try:
            if collection.count() == 0: return "（このチャンネルには、まだ何も記憶がないわ…）"
            query_embedding = await utils.get_embedding(query_text, task_type="RETRIEVAL_QUERY")
            if not query_embedding: return "（クエリのベクトル化に失敗して、検索できなかったわ）"
            where_filter = {"author_id": author_id} if author_id else {}
            results = collection.query(query_embeddings=[query_embedding], n_results=min(top_k * 2, collection.count()), where=where_filter or None, include=["metadatas", "documents", "distances"])
            if not results or not results.get('documents') or not results['documents'][0]: return "（このチャンネルには、関連する過去ログはないみたい…）"
            found_logs = []
            for i, doc in enumerate(results['documents'][0]):
                if results['distances'][0][i] > DISTANCE_THRESHOLD: continue
                metadata = results['metadatas'][0][i]
                log_entry = f"- {metadata.get('timestamp', '過去').split('T')[0]}, {metadata.get('author_name', '不明')}「{doc}」"
                found_logs.append(log_entry)
                if len(found_logs) >= top_k: break
            return "\n".join(found_logs) if found_logs else "（関連性の高い過去ログは見つからなかったわ…）"
        except Exception as e:
            print(f"FATAL Error during search_similar_messages: {e}"); traceback.print_exc()
            return f"（過去ログ検索中に致命的なエラーが発生したわ: {e}）"

    async def search_across_all_channels(self, query_text: str, guild: discord.Guild, top_k: int = 3):
        if not self.chroma_client or not query_text: return "（サーバー全体の記憶を検索できませんでした）"
        try:
            query_embedding = await utils.get_embedding(query_text, task_type="RETRIEVAL_QUERY")
            if not query_embedding: return "（クエリのベクトル化に失敗しました）"
            all_results = []
            for collection in self.chroma_client.list_collections():
                try:
                    channel_id = int(collection.name.replace(COLLECTION_NAME_PREFIX, ""))
                    if guild.get_channel(channel_id) is None: continue
                except (ValueError, TypeError): continue
                if collection.count() == 0: continue
                results = collection.query(query_embeddings=[query_embedding], n_results=min(top_k, collection.count()), include=["metadatas", "documents", "distances"])
                if results and results.get('documents') and results['documents'][0]:
                    for i, doc in enumerate(results['documents'][0]):
                        distance = results['distances'][0][i]
                        if distance <= (DISTANCE_THRESHOLD * 0.95):
                             all_results.append({"document": doc, "metadata": results['metadatas'][0][i], "distance": distance, "channel_id": channel_id})
            if not all_results: return "（サーバー全体で関連性の高い過去ログは見つかりませんでした）"
            sorted_results = sorted(all_results, key=lambda x: x['distance'])
            found_logs = []
            for result in sorted_results[:top_k]:
                channel = guild.get_channel(result["channel_id"])
                log_entry = f"- (#{channel.name if channel else '不明'}) {result['metadata'].get('timestamp', '過去').split('T')[0]}, {result['metadata'].get('author_name', '不明')}「{result['document']}」"
                found_logs.append(log_entry)
            return "\n".join(found_logs)
        except Exception as e:
            print(f"FATAL Error during search_across_all_channels: {e}"); traceback.print_exc()
            return f"（サーバー全体の過去ログ検索中にエラー発生: {e}）"

async def setup(bot): await bot.add_cog(DatabaseManager(bot))
