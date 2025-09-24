# cogs/_utils.py (更新版)
import os
import requests
from bs4 import BeautifulSoup
import json
import google.generativeai as genai # ★★★ 追加 ★★★
from . import _persona_manager as persona_manager

# --- 環境変数を読み込む ---
SEARCH_API_KEY = os.getenv('GOOGLE_SEARCH_API_KEY')
SEARCH_ENGINE_ID = os.getenv('GOOGLE_SEARCH_ENGINE_ID')
DATA_DIR = os.getenv('RAILWAY_VOLUME_MOUNT_PATH', '.')
MEMORY_FILE = os.path.join(DATA_DIR, 'bot_memory.json')

# ★★★ 新機能: どこからでも使えるベクトル化関数 ★★★
async def get_embedding(text: str, task_type="RETRIEVAL_DOCUMENT"):
    """テキストをベクトル化して返す"""
    if not text or not isinstance(text, str):
        return None
    try:
        result = await genai.embed_content_async(
            model="models/text-embedding-004",
            content=text,
            task_type=task_type
        )
        return result['embedding']
    except Exception as e:
        print(f"Embedding error: {e}")
        return None

def get_current_persona_name():
    """bot_memory.jsonから現在のペル-ソナ名を取得する"""
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            memory = json.load(f)
            return memory.get("server", {}).get("current_persona", persona_manager.DEFAULT_PERSONA)
    except (FileNotFoundError, json.JSONDecodeError):
        return persona_manager.DEFAULT_PERSONA

def get_current_persona():
    """現在のペルソナ設定をロードして返す"""
    persona_name = get_current_persona_name()
    return persona_manager.load_persona(persona_name)

def google_search(query: str, num_results: int = 5) -> dict | str:
    # (変更なし)
    if not SEARCH_API_KEY or not SEARCH_ENGINE_ID:
        error_msg = "（検索機能のAPIキーかエンジンIDが設定されてないんだけど？ アンタのミスじゃない？）"
        print(error_msg)
        return error_msg
    url = "https://www.googleapis.com/customsearch/v1"
    params = {'key': SEARCH_API_KEY, 'cx': SEARCH_ENGINE_ID, 'q': query, 'num': num_results}
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        results = response.json()
        return results.get('items', [])
    except Exception as e:
        error_msg = f"（検索中にエラーよ: {e}）"
        print(f"Google Search API error: {error_msg}")
        return error_msg

def scrape_url(url: str) -> str:
    # (変更なし)
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'lxml')
        main_content = soup.find('main') or soup.find('article') or soup.find('body')
        if main_content:
            for tag in main_content(['script', 'style', 'nav', 'footer', 'header', 'aside', 'form']):
                tag.decompose()
            text = ' '.join(main_content.get_text(separator=' ', strip=True).split())
            return text[:2000] if len(text) > 2000 else text
        return "（この記事、うまく読めなかったわ…）"
    except Exception as e:
        print(f"Scraping error for {url}: {e}")
        return f"（エラーでこの記事は読めなかったわ: {e}）"
