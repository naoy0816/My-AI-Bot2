# -------------------- Stage 1: ビルド環境 --------------------
# Pythonの軽量イメージをベースにする
FROM python:3.11-slim as builder

# 作業ディレクトリを設定
WORKDIR /app

# まず requirements.txt だけをコピーして、ライブラリをインストールする
# → requirements.txt に変更がない限り、この重い処理はキャッシュが使われ、スキップされる！
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# -------------------- Stage 2: 実行環境 --------------------
FROM python:3.11-slim as runtime

WORKDIR /app

# ビルド環境からインストール済みのライブラリだけをコピー
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# プロジェクトの全ファイルをコピー
COPY . .

# bot.py を実行するコマンド
CMD ["python3", "bot.py"]
