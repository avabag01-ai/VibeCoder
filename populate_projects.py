import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "vibecoder.db")

projects = [
    {
        "title": "Spectrogram-MIDI (Aegis Engine)",
        "slug": "spectrogram-midi-0206",
        "date": "2026-02-06",
        "description": "음악을 숫자로 번역하는 마법! 주식 차트 분석 기법을 기타 연주에 적용해봤습니다. 소음 가득한 환경에서도 내 기타 소리만 딱 집어내는 고정밀 MIDI 추출기입니다. 98% 정확도의 피치 트래킹과 멀티프로세싱 기반 실시간 처리를 자랑합니다.",
        "tech_stack": ["Python", "Computer Vision", "Signal Processing", "Multiprocessing"],
        "github_url": "https://github.com/avabag01-ai/spectrogram-midi",
        "demo_url": "",
        "thumbnail": "https://via.placeholder.com/800x450/0d0d14/a78bfa?text=Spectrogram-MIDI"
    },
    {
        "title": "One-Touch Map",
        "slug": "one-touch-map-0206",
        "date": "2026-02-06",
        "description": "배달 기사님들을 위한 초스피드 지도. 클릭 한 번으로 위치 저장하고, OCR로 주소 자동 입력까지! 전국 팔도 어디든 1초 만에 찾아가는 마이크로 서비스입니다. GPS 트래킹과 VWorld 지도 통합으로 실무 밀착형 바이브를 완성했습니다.",
        "tech_stack": ["JavaScript", "Leaflet", "GPS API", "OCR"],
        "github_url": "https://github.com/avabag01-ai/one-touch-map",
        "demo_url": "",
        "thumbnail": "https://via.placeholder.com/800x450/0d0d14/06b6d4?text=One-Touch+Map"
    },
    {
        "title": "Antigravity Ω-Proto (MCP)",
        "slug": "antigravity-omega-mcp-0208",
        "date": "2026-02-08",
        "description": "인간의 언어는 너무 느립니다. AI와 AI가 직접 대화하는 미래형 프로토콜 Ω(오메가). 데이터 전송 효율을 극대화하여 AI의 사고 속도를 날개 달아줍니다. 기존 대비 토큰 소모 77% 절감, 응답 속도 4배 향상의 벤치마크 결과를 확인하세요.",
        "tech_stack": ["Rust", "Python", "MCP", "HMC Compression"],
        "github_url": "https://github.com/avabag01-ai/antigravity-omega-mcp",
        "demo_url": "",
        "thumbnail": "https://via.placeholder.com/800x450/0d0d14/8b5cf6?text=Antigravity+Omega"
    },
    {
        "title": "SpreadRadar",
        "slug": "spread-radar-0222",
        "date": "2026-02-22",
        "description": "지갑은 뚱뚱하게, 검색은 얇게! 아마존과 네이버를 누비며 최저가를 사냥하는 AI 레이더입니다. 가격 비교부터 자동 포스팅까지 한 방에 해결하는 완벽한 수익 자동화 파이프라인입니다.",
        "tech_stack": ["Python", "Selenium", "LLM", "Automation"],
        "github_url": "https://github.com/avabag01-ai/SpreadRadar",
        "demo_url": "",
        "thumbnail": "https://via.placeholder.com/800x450/0d0d14/10b981?text=SpreadRadar"
    },
    {
        "title": "VibeCoder (Community)",
        "slug": "vibecoder-community-0222",
        "date": "2026-02-22",
        "description": "코딩을 '바이브'로 즐기는 사람들의 쉼터. 우리가 만든 결과물을 뽐내고, 서로의 프롬프트 꿀팁을 나누는 공간입니다. 익명 기반의 자유로운 소통과 프로젝트 쇼케이스를 지원합니다.",
        "tech_stack": ["Flask", "SQLite", "Docker", "Vibe Coding"],
        "github_url": "https://github.com/avabag01-ai/VibeCoder",
        "demo_url": "https://vibecoder-328967213016.asia-northeast3.run.app",
        "thumbnail": "https://via.placeholder.com/800x450/0d0d14/f59e0b?text=VibeCoder"
    }
]

def populate():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    print(f"Populating {len(projects)} projects into {DB_PATH}...")
    
    for p in projects:
        try:
            c.execute("""
                INSERT INTO projects (
                    created_at, title, slug, description, tech_stack, 
                    github_url, demo_url, thumbnail, author, is_featured
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (
                p["date"] + "T12:00:00",
                p["title"],
                p["slug"],
                p["description"],
                json.dumps(p["tech_stack"], ensure_ascii=False),
                p["github_url"],
                p["demo_url"],
                p["thumbnail"],
                "avabag01-ai"
            ))
            print(f"✅ Added: {p['title']}")
        except sqlite3.IntegrityError:
            print(f"⚠️ Skipped (already exists): {p['title']}")
        except Exception as e:
            print(f"❌ Error adding {p['title']}: {e}")
            
    conn.commit()
    conn.close()
    print("Done!")

if __name__ == "__main__":
    populate()
