"""
Supabase 데이터 저장 모듈
JSON 파일 대신 Supabase PostgreSQL(JSONB)에 데이터를 저장합니다.
"""

import os
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

_client = None


def get_client():
    """Supabase 클라이언트 싱글톤"""
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("SUPABASE_URL과 SUPABASE_KEY 환경변수를 설정해주세요.")
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def save_data(key: str, data):
    """데이터를 Supabase에 저장 (upsert)"""
    client = get_client()
    client.table("app_data").upsert({
        "key": key,
        "data": data
    }).execute()


def load_data(key: str):
    """Supabase에서 데이터 로드"""
    client = get_client()
    result = client.table("app_data").select("data").eq("key", key).execute()
    if result.data:
        return result.data[0]["data"]
    return None
