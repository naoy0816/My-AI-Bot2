# cogs/_utils.py (修正版)
import os
import requests
from bs4 import BeautifulSoup
from . import _persona_manager as persona_manager # ★★★ persona_managerをインポート ★★★

# --- 環境変数を読み込む ---
SEARCH_API_KEY = os.getenv('GOOGLE_SEARCH_API_KEY')
SEARCH_ENGINE_ID = os.getenv('GOOGLE_SEARCH_ENGINE_ID')
DATA_DIR = os.getenv('RAILWAY_VOLUME_MOUNT_PATH', '.') # ★★★ 追加 ★★★
MEMORY_FILE = os.path.join(DATA_DIR, 'bot_memory.json') # ★★★ 追加 ★★★

def get_current_persona_name():
    """bot_memory.jsonから現在のペルソナ名を取得する"""
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

# (google_search と scrape_url は変更なし)
def google_search(query: str, num_results: int = 5) -> dict | str:
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
    except requests.exceptions.RequestException as e:
        error_msg = f"（検索中にネットワークエラーよ。アンタの環境、ザコすぎなんじゃない？: {e}）"
        print(f"Google Search API error: {error_msg}")
        return error_msg
    except Exception as e:
        error_msg = f"（検索中に不明なエラーよ。アンタのAPIキーが間違ってるんじゃないの？w: {e}）"
        print(f"Google Search API error: {error_msg}")
        return error_msg

def scrape_url(url: str) -> str:
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
        return "（この記事、うまく読めなかったわ…主要なコンテンツが見つからないんだけど？）"
    except requests.exceptions.RequestException as e:
        print(f"Scraping error for {url}: {e}")
        return f"（エラーでこの記事は読めなかったわ: {e}）"
    except Exception as e:
        print(f"Scraping error for {url}: {e}")
        return f"（不明なエラーでこの記事は読めなかったわ: {e}）"
