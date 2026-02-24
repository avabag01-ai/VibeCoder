import sqlite3
import json
import os
import uuid
import requests
from datetime import datetime

# 데이터베이스 경로
DB_PATH = os.path.join(os.path.dirname(__file__), "vibecoder.db")

def generate_novelist_content():
    """
    소설가처럼 길고 은유적인 문체로 AI 트렌드를 생성합니다.
    기술적 노출을 피하면서도 깊이 있는 통찰을 담습니다.
    """
    date_str = datetime.now().strftime('%Y년 %m월 %d일')
    
    trends = [
        {
            "title": f"🌌 [Vibe Chronicle] {date_str}, 기계의 심장이 고동치는 방식",
            "content": f"""밤은 깊어가고, 화면 너머의 차가운 빛줄기는 우리 시대의 새로운 서사를 써내려가고 있습니다. {date_str} 오늘, 우리는 더 이상 명령어를 입력하지 않습니다. 우리는 거대한 지능의 파도와 '공명'하고 있습니다.

침묵하는 코드의 숲을 지나, 이제 AI는 스스로 길을 찾는 방랑자가 되었습니다. 이전의 기술들이 정교하게 조각된 기계 인형이었다면, 오늘날의 에이전틱(Agentic) 지능은 스스로 숨을 쉬며 목적지를 향해 항해하는 돛단배와 같습니다. 개발자는 이제 선원이 아니라, 바람의 방향을 읽고 돛을 조절하는 항해사가 되었습니다.

우리가 사용하는 '바이브'라는 단어는 단순히 유행어가 아닙니다. 그것은 논리의 차가운 족쇄를 풀고, 상상력이라는 뜨거운 엔진을 장착한 인류의 새로운 도약입니다. 커서(Cursor) 끝에서 피어오르는 한 줄의 영감은, 수만 명의 노동자가 쌓아 올린 바벨탑보다 더 높고 견고한 성을 단 몇 초 만에 세워 올립니다.

비용과 효율이라는 삭막한 단어들은 이제 '압축'과 '동기화'라는 은유 뒤로 숨어버렸습니다. 정보의 밀도가 높아질수록 우리의 대화는 더욱 간결해지고, 그 빈틈을 AI의 거대한 추론력이 메워줍니다. 이것은 기술의 발전이 아니라, 인류가 도구를 대하는 방식의 근본적인 '혁명'입니다.

오늘도 당신의 바이브는 어떤 운명의 실타래를 풀어내고 있습니까? 화면 속에서 깜빡이는 커서는 당신의 다음 문장을 기다리는 것이 아니라, 당신의 다음 '꿈'을 기다리고 있습니다.

#VibePhilosophy #AIEvolution #DigitalNomad #SpiritOfCoding""",
            "author": "VibeCron",
            "category": "info"
        },
        {
            "title": "🏹 [Deep-Insight] 보이지 않는 활시위: 에이전틱 지능의 은밀한 진화",
            "content": """우리는 흔히 기술을 손에 쥔 도구로 생각하지만, 지금 우리 곁을 흐르는 지능은 마치 스스로 목표를 찾아 날아가는 화살과 같습니다. 활사수가 화살의 궤적을 일일이 조정하지 않듯, 이제 우리는 '의도'라는 활시위를 당기기만 하면 됩니다. 목표 지점에 도달하기 위한 무수한 계산과 바람의 저항, 중력의 법칙은 AI라는 보이지 않는 비서가 찰나의 순간에 해결해 줍니다. 

사람들은 묻습니다. "코딩을 배우지 않아도 되는가?" 그 질문은 마치 "걸음을 배우지 않아도 되는가?"라는 질문과 같습니다. 우리는 걷기 위해 근육의 움직임을 계산하지 않습니다. 단지 가고 싶은 곳을 바라볼 뿐입니다. 바이브 코딩은 바로 그 지점을 지향합니다. 구현의 고통에서 해방되어, 오직 '가치'와 '아름다움'에만 집중할 수 있는 시대.

오늘 포착된 트렌드의 핵심은 '자율성'입니다. 도구가 스스로를 학습하고, 오류를 스스로 치유하며, 당신이 잠든 사이에도 당신의 비즈니스라는 정원을 가꾸는 것. 우리는 이제 정원사가 아니라, 어떤 꽃을 피울지 결정하는 설계자가 되어가고 있습니다.

#Agentic #Wisdom #SilentRevolution #VibeCoding""",
            "author": "VibeCron",
            "category": "info"
        }
    ]
    return trends

def post_to_lounge():
    if not os.path.exists(DB_PATH):
        # 만약 DB를 못 찾으면 스크립트 위치 기준으로 다시 검색
        local_db = "vibecoder.db"
        if os.path.exists(local_db):
            target_db = local_db
        else:
            print(f"❌ DB를 찾을 수 없습니다.")
            return
    else:
        target_db = DB_PATH

    trends = generate_novelist_content()
    conn = sqlite3.connect(target_db)
    c = conn.cursor()
    
    print(f"Generating {len(trends)} novelist-style trend updates...")
    
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
            print(f"✅ Novelist Trend Posted: {t['title']}")
        except Exception as e:
            print(f"❌ Error posting trend: {e}")
            
    conn.commit()
    conn.close()
    print("Long-form Trend Update Complete!")

if __name__ == "__main__":
    post_to_lounge()
