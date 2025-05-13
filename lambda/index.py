# lambda/index.py
import json
import os
import boto3
import re  # 正規表現モジュールをインポート
from botocore.exceptions import ClientError
import urllib.request
import urllib.error


# Lambda コンテキストからリージョンを抽出する関数
def extract_region_from_arn(arn):
    # ARN 形式: arn:aws:lambda:region:account-id:function:function-name
    match = re.search('arn:aws:lambda:([^:]+):', arn)
    if match:
        return match.group(1)
    return "us-east-1"  # デフォルト値

# 環境変数から FastAPI (ngrok 公開 URL) を取得
FASTAPI_ENDPOINT = os.environ.get("FASTAPI_ENDPOINT")
if not FASTAPI_ENDPOINT:
    raise RuntimeError("環境変数 'FASTAPI_ENDPOINT' が設定されていません")

# モデルID
MODEL_ID = os.environ.get("MODEL_ID", "us.amazon.nova-lite-v1:0")

def lambda_handler(event, context):
    try:
        print("Received event:", json.dumps(event))
        
        # Cognitoで認証されたユーザー情報を取得
        user_info = None
        if 'requestContext' in event and 'authorizer' in event['requestContext']:
            user_info = event['requestContext']['authorizer']['claims']
            print(f"Authenticated user: {user_info.get('email') or user_info.get('cognito:username')}")
        
        # リクエストボディの解析
        body = json.loads(event['body'])
        message = body['message']
        conversation_history = body.get('conversationHistory', [])
        
        print("Processing message:", message)
        print("Calling FastAPI at:", FASTAPI_ENDPOINT)
        print("Using model:", MODEL_ID)
        
        payload = json.dumps({
            "prompt": message,
            "max_new_tokens": 512,
            "do_sample": True,
            "temperature": 0.7,
            "top_p": 0.9
        }).encode("utf-8")

        req = urllib.request.Request(
            url=FASTAPI_ENDPOINT + "/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_body = resp.read().decode("utf-8")
        api_resp = json.loads(resp_body)
        # FastAPI のレスポンスが GenerationResponse 型 => {"generated_text": "...", "response_time": ...}
        assistant_response = api_resp.get("generated_text", "")
        if not assistant_response:
            raise Exception("Empty response from FastAPI")
        
        # 会話履歴を使用
        messages = conversation_history.copy()
        
        # ユーザーメッセージを追加
        messages.append({
            "role": "user",
            "content": message
        })


        messages.append({
            "role": "assistant",
            "content": assistant_response
            })
        
        # 成功レスポンスの返却
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Allow-Methods": "OPTIONS,POST"
            },
            "body": json.dumps({
                "success": True,
                "response": assistant_response,
                "conversationHistory": messages
            })
        }
        
    except urllib.error.HTTPError as e:
        print("HTTPError:", e.code, e.reason)
        error_msg = f"HTTPError {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        print("URLError:", e.reason)
        error_msg = f"URLError: {e.reason}"
    except Exception as error:
        print("Error:", str(error))
        error_msg = str(error)

    # エラー時レスポンス
    return {
        "statusCode": 500,
        "headers": {
            "Content-Type":                "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers":"Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods":"OPTIONS,POST"
        },
        "body": json.dumps({
            "success": False,
            "error": error_msg
        })
    }
