import sqlite3
import json
import os
import uuid
import requests
from datetime import datetime

# 데이터베이스 경로 (VibeCoder 위치에 맞게 조정 필요)
DB_PATH = os.path.join(os.path.dirname(__file__), "vibecoder.db")

def get_latest_trends():
    """
    실제 환경에서는 뉴스 API나 검색 API를 사용하겠지만, 
    여기서는 최신 2026년 2월 트렌드를 기반으로 자동 생성 로직을 시뮬레이션합니다.
    """
    trends = [
        {
            "title": f"[Trend Master] {datetime.now().strftime('%m.%d')} AI 코딩 실시간 핫토픽 🚀",
            "content": """오늘의 바이브 코딩 동향을 요약해 드립니다.

1. **Agentic Workflow의 확산**: 이제 단순 수정을 넘어, 전체 아키텍처를 설계하고 스스로 테스트까지 마치는 '에이전틱 워크플로우'가 대세입니다.
2. **DeepSeek-R1 vs Claude 3.5**: 추론형 모델들 간의 코딩 대결이 치열합니다. 복잡한 로직은 R1으로, 세련된 UI는 Claude로 짜는 '믹스 전략'이 유행 중입니다.
3. **Small Language Models (SLM)의 약진**: 로컬 기기에서 인터넷 없이도 돌아가는 강력한 소형 모델들이 바이브 코더들의 개인 서버(Private Cloud) 구축을 돕고 있습니다.

바이브는 멈추지 않습니다. 오늘의 코딩 온도는 '열정'입니다! #AI_Trends #VibeCoding #DailyUpdate""",
            "author": "VibeBot_v1.0",
            "category": "info"
        }
    ]
    return trends

def post_to_lounge():
    if not os.path.exists(DB_PATH):
        print(f"❌ DB를 찾을 수 없습니다: {DB_PATH}")
        return

    trends = get_latest_trends()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    print(f"Post-processing {len(trends)} trend updates...")
    
    for t in trends:
        slug = f"trend-{datetime.now().strftime('%m%d%H%M')}-{str(uuid.uuid4())[:4]}"
        try:
            c.execute("""
                INSERT INTO posts (
                    created_at, title, slug, content, category, author_name, is_spam
                ) VALUES (?, ?, ?, ?, ?, ?, 0)
            """, (
                datetime.now().isoformat(),
                t["title"],
                slug,
                t["content"],
                t["category"],
                t["author"]
            ))
            print(f"✅ Trend Posted: {t['title']}")
        except Exception as e:
            print(f"❌ Error posting trend: {e}")
            
    conn.commit()
    conn.close()
    print("Trend Update Complete!")

if __name__ == "__main__":
    post_to_lounge()
