# cogs/utils.py (新規作成)
import os
import requests
from bs4 import BeautifulSoup

# --- 環境変数を読み込む ---
SEARCH_API_KEY = os.getenv('GOOGLE_SEARCH_API_KEY')
SEARCH_ENGINE_ID = os.getenv('GOOGLE_SEARCH_ENGINE_ID')

def google_search(query: str, num_results: int = 5) -> dict | str:
    """
    Google Custom Search APIを使ってWeb検索を実行する。
    成功した場合は検索結果のリスト(dict)を、失敗した場合はエラーメッセージ(str)を返す。
    """
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
    """
    指定されたURLの本文を抽出して返す。
    """
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'lxml')
        
        # 主要なコンテンツが含まれていそうなタグを優先的に探す
        main_content = soup.find('main') or soup.find('article') or soup.find('body')
        
        if main_content:
            # 不要なタグ（ナビゲーション、フッター、広告など）を削除
            for tag in main_content(['script', 'style', 'nav', 'footer', 'header', 'aside', 'form']):
                tag.decompose()
            
            # テキストを抽出して、余計な空白や改行を整理
            text = ' '.join(main_content.get_text(separator=' ', strip=True).split())
            
            # 長すぎる場合は2000文字に制限
            return text[:2000] if len(text) > 2000 else text
            
        return "（この記事、うまく読めなかったわ…主要なコンテンツが見つからないんだけど？）"
    except requests.exceptions.RequestException as e:
        print(f"Scraping error for {url}: {e}")
        return f"（エラーでこの記事は読めなかったわ: {e}）"
    except Exception as e:
        print(f"Scraping error for {url}: {e}")
        return f"（不明なエラーでこの記事は読めなかったわ: {e}）"
