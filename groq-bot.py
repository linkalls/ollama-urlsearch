import os
import re
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, abort
from groq import Groq
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
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

# .env ファイルを読み込む
load_dotenv()

app = Flask(__name__)

# 環境変数を取得
access_token = os.getenv('ACCESS_TOKEN')
channel_secret = os.getenv('CHANNEL_SECRET')
groq_api_key = os.getenv('GROQ_API_KEY')

if not groq_api_key:
    raise ValueError("GROQ_API_KEYが設定されていません。")

configuration = Configuration(access_token=access_token)
handler = WebhookHandler(channel_secret)

# Groqクライアントの初期化
groq_client = Groq(api_key=groq_api_key)

# URLのタイトルと本文を取得する関数
def fetch_title_and_body(url):
    print(f"fetch_title_and_body: URLを取得中 - {url}")
    
    # Seleniumの設定
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # ヘッドレスモードで実行
    chrome_options.add_argument("--ignore-certificate-errors")  # SSLエラーを無視
    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
    
    driver.get(url)
    
    # ページタイトルを取得
    title = driver.title
    print(f"fetch_title_and_body: タイトルを取得 - {title}")
    
    # Yahoo Newsの場合、特定のクラスを持つ段落のみを取得
    if "news.yahoo.co.jp" in url:
        paragraphs = driver.find_elements(By.CSS_SELECTOR, 'p.sc-54nboa-0.deLyrJ.yjSlinkDirectlink.highLightSearchTarget')
    else:
        # その他のサイトの場合、全ての段落を取得
        paragraphs = driver.find_elements(By.TAG_NAME, 'p')
    
    if paragraphs:
        body = '\n'.join([p.text for p in paragraphs])
    else:
        body = "本文を取得できませんでした。"
    print(f"fetch_title_and_body: 本文を取得 - {body[:100]}...")  # 本文の最初の100文字を表示
    
    driver.quit()
    
    return title, body

# Groq APIを使ってテキストを要約する関数
def summarize_text(title, body):
    print(f"summarize_text: 要約を開始 - タイトル: {title}")
    model = "gemma2-9b-it"  # Groqのモデル名

    # システムプロンプト (要約内容に関する詳細な指示)
    system_prompt = (
     "Please always only reply in Japanese.!!!!!!! It is the most important thing."
    "Please include the title and main points of the text in your summary so that it can be understood without reading the text."
    "Avoid subjective opinions or unnecessary details."
    "Focus on the most important factual information."
    "Please summarize the following text in four lines or less."
    "Use only what the text says, not your knowledge."
    )

    
    # 要約のためのプロンプト作成
    prompt = f"{system_prompt}\n\nタイトル: {title}\n本文: {body}"
    print(f"summarize_text: プロンプトを作成 - {prompt[:100]}...")  # プロンプトの最初の100文字を表示
    
    # Groq APIへ要約リクエスト
    response = groq_client.chat.completions.create(model=model, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": body}], max_tokens=8000, temperature=1.2)
    print(f"summarize_text: APIレスポンス - {response}")

    # レスポンスに'choices'フィールドが存在するか確認
    if response.choices and len(response.choices) > 0:
        summary = response.choices[0].message.content
        print(f"summarize_text: 要約を取得 - {summary}")
        return summary
    else:
        print("summarize_text: 'choices'フィールドがレスポンスに存在しません")
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
        
        # Groq APIを使って要約を実行
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