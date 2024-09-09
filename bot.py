import os
import re
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, abort
import ollama
from linebot.v3 import (
    WebhookHandler
)
from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent
)

from dotenv import load_dotenv
# .env ファイルを読み込む
load_dotenv()

app = Flask(__name__)

# 環境変数を取得
access_token = os.getenv('ACCESS_TOKEN')
channel_secret = os.getenv('CHANNEL_SECRET')

configuration = Configuration(access_token=access_token)
handler = WebhookHandler(channel_secret)

# URLのタイトルと本文を取得する関数
def fetch_title_and_body(url):
    print(f"fetch_title_and_body: URLを取得中 - {url}")
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    # ページタイトルを取得
    title = soup.title.string if soup.title else "No Title"
    print(f"fetch_title_and_body: タイトルを取得 - {title}")

    # 本文を特定のタグやクラスから抽出
    article_body = soup.find('div', {'class': 'ArticleBody__content___2gQno'})
    if article_body:
        paragraphs = article_body.find_all('p')
        body = '\n'.join([p.get_text() for p in paragraphs])
    else:
        body = "本文を取得できませんでした。"
    print(f"fetch_title_and_body: 本文を取得 - {body[:100]}...")  # 本文の最初の100文字を表示

    return title, body

# Ollama APIを使ってテキストを要約する関数
def summarize_text(title, body):
    print(f"summarize_text: 要約を開始 - タイトル: {title}")
    model = "gemma2:2b"  # Ollamaのモデル名

    # システムプロンプト (要約内容に関する詳細な指示)
    system_prompt = (
    "Please reply in Japanese."
    "Please summarize the following text in three lines or less."
    "Please be concise and include key points in your summary."
    "Please include the title and main points of the text in your summary so that it can be understood without reading the text."
    "Ensure that the summary is coherent and logically structured."
    "Avoid subjective opinions or unnecessary details."
    "Focus on the most important factual information."
    )

    
    # 要約のためのプロンプト作成
    prompt = f"{system_prompt}\n\nタイトル: {title}\n本文: {body}"
    print(f"summarize_text: プロンプトを作成 - {prompt[:100]}...")  # プロンプトの最初の100文字を表示
    
    # Ollama APIへ要約リクエスト
    response = ollama.chat(model=model, messages=[{"role": "system", "content": prompt}])
    print(f"summarize_text: APIレスポンス - {response}")

    # レスポンスに'message'フィールドが存在するか確認
    if 'message' in response and 'content' in response['message']:
        summary = response['message']['content']
        print(f"summarize_text: 要約を取得 - {summary}")
        return summary
    else:
        print("summarize_text: 'message'フィールドがレスポンスに存在しません")
        return "要約を取得できませんでした。"

# LINE botのWebhook設定 (LINEからのリクエスト受け取り)
@app.route("/callback", methods=['POST'])
def callback():
    print("callback: リクエストを受信")
    # LINEからのリクエストの署名を検証
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
        print("callback: リクエストの処理に成功")
    except InvalidSignatureError:
        print("callback: Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'

# メッセージイベントのハンドラ (LINEでメッセージを受け取ったときの処理)
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    print(f"handle_message: メッセージを受信 - {event.message.text}")
    message_text = event.message.text

    # メッセージにURLが含まれているかを正規表現でチェック
    url_pattern = re.compile(r'https?://[^\s]+')
    urls = url_pattern.findall(message_text)

    if urls:
        # 最初に見つかったURLを処理対象とする
        url = urls[0]
        print(f"handle_message: URLを検出 - {url}")
        
        # URLの内容（タイトルと本文）を取得
        title, body = fetch_title_and_body(url)
        
        # Ollama APIを使って要約を実行
        summary = summarize_text(title, body)

        # タイトルと要約を返信
        reply_text = f"タイトル: {title}\n要約: {summary}"
        print(f"handle_message: 返信メッセージを作成 - {reply_text}")
        
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply_text)]
                )
            )
    else:
        print("handle_message: URLが検出されませんでした")

if __name__ == "__main__":
    print("アプリケーションを起動中...")
    app.run(host='0.0.0.0', port=5000)