# ⚡ VibeCoder

바이브 코더들의 프로젝트 쇼케이스 & 커뮤니티

## 🚀 주요 기능
- **쇼케이스**: AI로 만든 프로젝트 갤러리
- **코더스 라운지**: 가입 없는 익명 커뮤니티 (꿀팁/Q&A/자유)
- **익명 시스템**: 닉네임+비밀번호만으로 게시/수정/삭제
- **스팸 방지**: IP 속도제한 + 룰 기반 필터
- **세션 쿠키**: 본인 글 자동 식별

## 🏃 로컬 실행
```bash
pip install -r requirements.txt
python app.py
```

## 🌐 배포 (Render.com)
1. GitHub 연결
2. Environment Variables: `SECRET_KEY`, `DATABASE_URL`
3. Start Command: `gunicorn app:app`
