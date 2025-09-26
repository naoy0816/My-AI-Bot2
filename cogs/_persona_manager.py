import json
import os

# ★★★ ここが間違ってたわよ！★★★
# アタシの人格（ペルソナ）が保管されてる場所を正しく修正したわ
PERSONA_DIR = './cogs/personas' 
DEFAULT_PERSONA = 'mesugaki'

def get_persona_path(persona_name):
    """ペルソナファイルのパスを取得する"""
    return os.path.join(PERSONA_DIR, f"{persona_name}.json")

def load_persona(persona_name=None):
    """指定されたペルソナファイルを読み込む。なければデフォルトを読み込む。"""
    if persona_name is None:
        persona_name = DEFAULT_PERSONA
    
    filepath = get_persona_path(persona_name)
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # 指定されたファイルがなければ、デフォルトを試す
        print(f"Warning: Persona file '{persona_name}.json' not found or corrupted. Loading default persona.")
        filepath = get_persona_path(DEFAULT_PERSONA)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # デフォルトすらない場合はエラーを返す
            print(f"FATAL: Default persona file '{DEFAULT_PERSONA}.json' not found or corrupted.")
            return None

def list_personas():
    """利用可能なペルソナのリストを返す"""
    if not os.path.exists(PERSONA_DIR):
        return []
    
    personas = []
    for filename in os.listdir(PERSONA_DIR):
        if filename.endswith('.json'):
            try:
                with open(os.path.join(PERSONA_DIR, filename), 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    personas.append({
                        "id": filename[:-5],
                        "name": data.get("name", "名前なし"),
                        "description": data.get("description", "説明なし")
                    })
            except (json.JSONDecodeError, KeyError):
                continue
    return personas
