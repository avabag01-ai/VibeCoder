"""
VibeCoder — 바이브 코더 커뮤니티
익명 기반 인터랙션 아키텍처:
  L1: 완전 익명 (닉네임+비번만)
  L2: 세션 쿠키 기반 식별 (본인 글 수정)
  L3: 스팸 방지 (IP 속도제한 + 룰 기반 필터)
"""

import os
import re
import json
import uuid
import bcrypt
import time
import threading
import urllib.request
from datetime import datetime, timedelta
from xml.etree import ElementTree
from flask import (
    Flask, render_template, request, redirect,
    url_for, jsonify, abort, make_response
)
from dotenv import load_dotenv

# ── AI 뉴스 캐시 (1시간마다 갱신) ──
_news_cache = {"data": [], "updated": 0}
_news_lock = threading.Lock()

RSS_FEEDS = [
    ("TechCrunch AI",   "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("The Verge AI",    "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml"),
    ("VentureBeat AI",  "https://venturebeat.com/category/ai/feed/"),
    ("MIT Tech Review", "https://www.technologyreview.com/feed/"),
    ("AI News",         "https://www.artificialintelligence-news.com/feed/"),
]

def _parse_date(s):
    if not s: return "최근"
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(s)
        diff = datetime.now(dt.tzinfo) - dt
        h = int(diff.total_seconds() / 3600)
        if h < 1: return "방금 전"
        if h < 24: return f"{h}시간 전"
        return f"{diff.days}일 전"
    except: return "최근"

def _fetch_news():
    items = []
    for src, url in RSS_FEEDS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                root = ElementTree.fromstring(r.read())
            for item in root.findall(".//item")[:4]:
                title = re.sub(r"<[^>]+>", "", item.findtext("title", ""))
                link  = item.findtext("link", "") or item.findtext("guid", "")
                date  = _parse_date(item.findtext("pubDate", ""))
                if title and link:
                    items.append({"source": src, "title": title[:120], "url": link, "time": date})
        except: pass
    return items[:18]

def get_ai_news():
    """캐시된 AI 뉴스 반환 (1시간 캐시)"""
    with _news_lock:
        if time.time() - _news_cache["updated"] > 3600:
            data = _fetch_news()
            if data:
                _news_cache["data"] = data
                _news_cache["updated"] = time.time()
        return _news_cache["data"]

load_dotenv()

from db import get_conn, init_db, ph, fetchall, fetchone

app = Flask(__name__, static_folder="static", template_folder="static")
app.secret_key = os.environ.get("SECRET_KEY", "vibecoder-dev-2025")

# ── 스팸 필터 키워드 ──
SPAM_KEYWORDS = [
    "카지노", "바카라", "토토", "먹튀", "베팅", "불법", "도박",
    "비트코인 투자", "forex", "주식 추천", "대출 광고",
    "클릭 하세요", "바로가기", "광고", "홍보합니다",
]
# 최소 글자수
MIN_CONTENT_LEN = 10
# IP당 분당 최대 게시 횟수
RATE_LIMIT_PER_MIN = 3


# ──────────────────────────────────────────────────────────
# 유틸
# ──────────────────────────────────────────────────────────
def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:80]


def hash_password(raw: str) -> str:
    """bcrypt 해시 (cost factor 12)"""
    return bcrypt.hashpw(raw.encode(), bcrypt.gensalt(rounds=12)).decode()


def check_password(raw: str, hashed: str) -> bool:
    """bcrypt 검증 (구 sha256 fallback 포함)"""
    if not raw or not hashed:
        return False
    # 구 sha256 해시(64자 hex) 호환성 유지
    if len(hashed) == 64 and all(c in "0123456789abcdef" for c in hashed):
        import hashlib
        return hashlib.sha256(raw.encode()).hexdigest() == hashed
    try:
        return bcrypt.checkpw(raw.encode(), hashed.encode())
    except Exception:
        return False


def get_session_token(resp=None):
    """브라우저 쿠키에서 세션 토큰 읽기/생성"""
    token = request.cookies.get("vc_session")
    if not token:
        token = str(uuid.uuid4())
        if resp:
            resp.set_cookie("vc_session", token, max_age=60*60*24*365, httponly=True, samesite="Lax")
    return token


def get_client_ip() -> str:
    """실제 IP 추출 (Render/프록시 환경 대응)"""
    return (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.remote_addr
        or "unknown"
    )


def is_spam(title: str, content: str) -> bool:
    """룰 기반 스팸 판별"""
    text = (title + " " + content).lower()
    # 1. 금지 키워드
    for kw in SPAM_KEYWORDS:
        if kw.lower() in text:
            return True
    # 2. URL 도배 (5개 이상 링크)
    url_count = len(re.findall(r'https?://', text))
    if url_count >= 5:
        return True
    # 3. 너무 짧은 내용
    if len(content.strip()) < MIN_CONTENT_LEN:
        return True
    # 4. 같은 문자 반복 (aaaaaaa 같은)
    if re.search(r'(.)\1{9,}', text):
        return True
    return False


def check_rate_limit(ip: str, action: str = "post") -> bool:
    """IP당 1분 내 RATE_LIMIT_PER_MIN 초과 시 True (차단)"""
    conn = get_conn()
    c = conn.cursor()
    p = ph()
    cutoff = (datetime.now() - timedelta(minutes=1)).isoformat()
    c.execute(
        f"SELECT COUNT(*) as cnt FROM rate_limits WHERE ip_address={p} AND action={p} AND created_at>{p}",
        (ip, action, cutoff)
    )
    row = fetchone(c)
    count = row["cnt"] if row else 0
    conn.close()
    return count >= RATE_LIMIT_PER_MIN


def record_action(ip: str, action: str = "post"):
    """속도 제한 카운터 기록"""
    conn = get_conn()
    c = conn.cursor()
    p = ph()
    c.execute(
        f"INSERT INTO rate_limits (ip_address, action, created_at) VALUES ({p},{p},{p})",
        (ip, action, datetime.now().isoformat())
    )
    # 오래된 레코드 정리 (1시간 이상)
    cutoff = (datetime.now() - timedelta(hours=1)).isoformat()
    c.execute(f"DELETE FROM rate_limits WHERE created_at < {p}", (cutoff,))
    conn.commit()
    conn.close()


def fmt_date(dt_str):
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(dt_str)
        diff = datetime.now() - dt
        if diff.seconds < 60:
            return "방금 전"
        if diff.seconds < 3600:
            return f"{diff.seconds//60}분 전"
        if diff.days == 0:
            return f"{diff.seconds//3600}시간 전"
        if diff.days < 7:
            return f"{diff.days}일 전"
        return dt.strftime("%m.%d")
    except Exception:
        return dt_str[:10] if len(dt_str) >= 10 else dt_str


# Jinja2 필터 등록
app.jinja_env.filters['fmt_date'] = fmt_date


# ──────────────────────────────────────────────────────────
# 메인 / 홈
# ──────────────────────────────────────────────────────────
@app.route("/")
def index():
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT * FROM projects WHERE is_featured=1 ORDER BY created_at DESC LIMIT 6")
    featured = fetchall(c)

    c.execute("SELECT * FROM posts WHERE is_spam=0 AND is_deleted=0 ORDER BY created_at DESC LIMIT 5")
    latest_posts = fetchall(c)

    c.execute("SELECT * FROM posts WHERE category='info' AND is_spam=0 AND is_deleted=0 ORDER BY created_at DESC LIMIT 3")
    trend_news = fetchall(c)

    c.execute("SELECT COUNT(*) as cnt FROM projects")
    project_count = fetchone(c)["cnt"]

    c.execute("SELECT COUNT(*) as cnt FROM posts WHERE is_spam=0 AND is_deleted=0")
    post_count = fetchone(c)["cnt"]

    conn.close()

    for proj in featured:
        if proj.get("tech_stack"):
            try:
                proj["tech_stack"] = json.loads(proj["tech_stack"])
            except Exception:
                proj["tech_stack"] = []

    # AI 뉴스 (캐시, 1시간 갱신)
    ai_news = get_ai_news()

    record_pageview("/")
    return render_template("index.html",
        featured=featured,
        latest_posts=latest_posts,
        trend_news=trend_news,
        project_count=project_count,
        post_count=post_count,
        ai_news=ai_news,
    )


# ──────────────────────────────────────────────────────────
# 쇼케이스
# ──────────────────────────────────────────────────────────
@app.route("/showcase")
def showcase():
    conn = get_conn()
    c = conn.cursor()

    page = max(1, request.args.get("page", 1, type=int))
    per_page = 12
    offset = (page - 1) * per_page
    p = ph()

    c.execute(
        f"SELECT * FROM projects ORDER BY is_featured DESC, created_at DESC LIMIT {p} OFFSET {p}",
        (per_page, offset),
    )
    projects = fetchall(c)

    c.execute("SELECT COUNT(*) as cnt FROM projects")
    total = fetchone(c)["cnt"]
    conn.close()

    for proj in projects:
        if proj.get("tech_stack"):
            try:
                proj["tech_stack"] = json.loads(proj["tech_stack"])
            except Exception:
                proj["tech_stack"] = []

    record_pageview("/showcase")
    return render_template("showcase.html",
        projects=projects,
        page=page,
        total_pages=(total + per_page - 1) // per_page,
        total=total,
    )


@app.route("/trends")
def trends():
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM posts WHERE category='info' AND is_spam=0 AND is_deleted=0 ORDER BY created_at DESC LIMIT 20"
    )
    news_items = fetchall(c)
    conn.close()

    ai_news = get_ai_news()
    record_pageview("/trends")
    return render_template("trends.html", news_items=news_items, ai_news=ai_news)


@app.route("/api/ai-news")
def api_ai_news():
    """실시간 AI 뉴스 API (1시간 캐시)"""
    news = get_ai_news()
    return jsonify({"ok": True, "news": news, "count": len(news)})


@app.route("/showcase/<slug>")
def project_detail(slug):
    conn = get_conn()
    c = conn.cursor()
    p = ph()

    c.execute(f"SELECT * FROM projects WHERE slug={p}", (slug,))
    proj = fetchone(c)
    if not proj:
        conn.close(); abort(404)

    c.execute(f"UPDATE projects SET view_count=view_count+1 WHERE slug={p}", (slug,))
    conn.commit()

    if proj.get("tech_stack"):
        try:
            proj["tech_stack"] = json.loads(proj["tech_stack"])
        except Exception:
            proj["tech_stack"] = []

    c.execute(
        f"SELECT * FROM comments WHERE project_id={p} AND is_approved=1 AND is_deleted=0 ORDER BY created_at ASC",
        (proj["id"],),
    )
    comments = fetchall(c)
    conn.close()

    session_token = request.cookies.get("vc_session", "")
    return render_template("project.html", proj=proj, comments=comments, session_token=session_token)


@app.route("/showcase/<slug>/like", methods=["POST"])
def project_like(slug):
    conn = get_conn()
    c = conn.cursor()
    p = ph()
    c.execute(f"UPDATE projects SET likes=likes+1 WHERE slug={p}", (slug,))
    conn.commit()
    c.execute(f"SELECT likes FROM projects WHERE slug={p}", (slug,))
    row = fetchone(c)
    conn.close()
    return jsonify({"likes": row["likes"] if row else 0})


# ──────────────────────────────────────────────────────────
# 프로젝트 제출 (익명)
# ──────────────────────────────────────────────────────────
@app.route("/submit", methods=["GET", "POST"])
def submit():
    error = None
    if request.method == "POST":
        ip = get_client_ip()

        # 속도 제한 체크
        if check_rate_limit(ip, "project"):
            error = "잠시 후 다시 시도해주세요. (1분 최대 3회)"
            return render_template("submit.html", error=error)

        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        tech_raw = request.form.get("tech_stack", "").strip()
        demo_url = request.form.get("demo_url", "").strip()
        github_url = request.form.get("github_url", "").strip()
        thumbnail = request.form.get("thumbnail", "").strip()
        author = request.form.get("author", "익명코더").strip() or "익명코더"

        if not title:
            return render_template("submit.html", error="제목을 입력해주세요.")
        if is_spam(title, description):
            return render_template("submit.html", error="스팸으로 감지된 내용입니다.")

        tech_list = [t.strip() for t in tech_raw.split(",") if t.strip()]
        slug = slugify(title) + "-" + datetime.now().strftime("%m%d%H%M")

        conn = get_conn()
        c = conn.cursor()
        p = ph()
        try:
            c.execute(
                f"""INSERT INTO projects
                    (created_at, title, slug, description, tech_stack,
                     demo_url, github_url, thumbnail, author, is_featured, ip_address)
                    VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},0,{p})""",
                (
                    datetime.now().isoformat(), title, slug, description,
                    json.dumps(tech_list, ensure_ascii=False),
                    demo_url, github_url, thumbnail, author, ip,
                ),
            )
            conn.commit()
            conn.close()
            record_action(ip, "project")
            return redirect(url_for("project_detail", slug=slug))
        except Exception as e:
            conn.close()
            return render_template("submit.html", error=f"저장 실패: {e}")

    return render_template("submit.html", error=error)


# ──────────────────────────────────────────────────────────
# 라운지 (익명 게시판)
# ──────────────────────────────────────────────────────────
@app.route("/lounge")
def lounge():
    conn = get_conn()
    c = conn.cursor()

    page = max(1, request.args.get("page", 1, type=int))
    category = request.args.get("category", "")
    per_page = 20
    offset = (page - 1) * per_page
    p = ph()

    base_where = "is_spam=0 AND is_deleted=0"

    if category:
        c.execute(
            f"SELECT * FROM posts WHERE {base_where} AND category={p} ORDER BY created_at DESC LIMIT {p} OFFSET {p}",
            (category, per_page, offset),
        )
        c2 = conn.cursor()
        c2.execute(f"SELECT COUNT(*) as cnt FROM posts WHERE {base_where} AND category={p}", (category,))
    else:
        c.execute(
            f"SELECT * FROM posts WHERE {base_where} ORDER BY created_at DESC LIMIT {p} OFFSET {p}",
            (per_page, offset),
        )
        c2 = conn.cursor()
        c2.execute(f"SELECT COUNT(*) as cnt FROM posts WHERE {base_where}")

    posts = fetchall(c)
    total = fetchone(c2)["cnt"]
    conn.close()

    session_token = request.cookies.get("vc_session", "")

    record_pageview("/lounge")
    return render_template("lounge.html",
        posts=posts,
        page=page,
        total_pages=(total + per_page - 1) // per_page,
        total=total,
        category=category,
        session_token=session_token,
    )


@app.route("/lounge/write", methods=["GET", "POST"])
def lounge_write():
    error = None

    if request.method == "POST":
        ip = get_client_ip()

        # 속도 제한
        if check_rate_limit(ip, "post"):
            error = "잠시 후 다시 시도해주세요. (1분 최대 3회)"
            return render_template("lounge_write.html", error=error)

        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        category = request.form.get("category", "free").strip()
        author = request.form.get("author", "익명코더").strip() or "익명코더"
        password = request.form.get("password", "").strip()
        tags = request.form.get("tags", "").strip()

        if not title:
            return render_template("lounge_write.html", error="제목을 입력해주세요.")
        if not content or len(content) < MIN_CONTENT_LEN:
            return render_template("lounge_write.html", error=f"내용을 {MIN_CONTENT_LEN}자 이상 입력해주세요.")

        spam = is_spam(title, content)
        slug = slugify(title) + "-" + datetime.now().strftime("%m%d%H%M")
        pw_hash = hash_password(password) if password else None

        # 세션 토큰
        session_token = request.cookies.get("vc_session") or str(uuid.uuid4())

        conn = get_conn()
        c = conn.cursor()
        p = ph()
        try:
            c.execute(
                f"""INSERT INTO posts
                    (created_at, title, slug, content, category, author_name,
                     password_hash, session_token, ip_address, tags, is_spam)
                    VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p})""",
                (
                    datetime.now().isoformat(), title, slug, content, category,
                    author, pw_hash, session_token, ip, tags,
                    1 if spam else 0,
                ),
            )
            conn.commit()
            conn.close()
            record_action(ip, "post")

            resp = make_response(redirect(url_for("lounge_post", slug=slug)))
            resp.set_cookie("vc_session", session_token, max_age=60*60*24*365, httponly=True, samesite="Lax")
            return resp
        except Exception as e:
            conn.close()
            return render_template("lounge_write.html", error=f"저장 실패: {e}")

    return render_template("lounge_write.html", error=error)


@app.route("/lounge/<slug>")
def lounge_post(slug):
    conn = get_conn()
    c = conn.cursor()
    p = ph()

    c.execute(f"SELECT * FROM posts WHERE slug={p} AND is_deleted=0", (slug,))
    post = fetchone(c)
    if not post:
        conn.close(); abort(404)

    if not post.get("is_spam"):
        c.execute(f"UPDATE posts SET view_count=view_count+1 WHERE slug={p}", (slug,))
        conn.commit()

    c.execute(
        f"SELECT * FROM comments WHERE post_id={p} AND is_approved=1 AND is_deleted=0 ORDER BY created_at ASC",
        (post["id"],),
    )
    comments = fetchall(c)
    conn.close()

    session_token = request.cookies.get("vc_session", "")
    can_edit = session_token and session_token == post.get("session_token")

    return render_template("lounge_post.html",
        post=post, comments=comments,
        can_edit=can_edit, session_token=session_token,
    )


@app.route("/lounge/<slug>/like", methods=["POST"])
def post_like(slug):
    conn = get_conn()
    c = conn.cursor()
    p = ph()
    c.execute(f"UPDATE posts SET likes=likes+1 WHERE slug={p}", (slug,))
    conn.commit()
    c.execute(f"SELECT likes FROM posts WHERE slug={p}", (slug,))
    row = fetchone(c)
    conn.close()
    return jsonify({"likes": row["likes"] if row else 0})


@app.route("/lounge/<slug>/delete", methods=["POST"])
def post_delete(slug):
    """세션 쿠키 or 비밀번호로 본인 글 삭제 (soft delete)"""
    conn = get_conn()
    c = conn.cursor()
    p = ph()

    c.execute(f"SELECT * FROM posts WHERE slug={p}", (slug,))
    post = fetchone(c)
    if not post:
        conn.close(); abort(404)

    session_token = request.cookies.get("vc_session", "")
    password = request.form.get("password", "")

    can_delete = (
        (session_token and session_token == post.get("session_token")) or
        check_password(password, post.get("password_hash") or "")
    )

    if can_delete:
        c.execute(f"UPDATE posts SET is_deleted=1 WHERE slug={p}", (slug,))
        conn.commit()
        conn.close()
        return redirect(url_for("lounge"))
    else:
        conn.close()
        return redirect(url_for("lounge_post", slug=slug) + "?error=비밀번호가 틀렸습니다.")


# ──────────────────────────────────────────────────────────
# 댓글 (익명)
# ──────────────────────────────────────────────────────────
@app.route("/comment", methods=["POST"])
def add_comment():
    ip = get_client_ip()

    # 속도 제한
    if check_rate_limit(ip, "comment"):
        return redirect(request.form.get("redirect_url", "/") + "?error=잠시후재시도")

    post_id = request.form.get("post_id", type=int)
    project_id = request.form.get("project_id", type=int)
    author = request.form.get("author", "익명코더").strip() or "익명코더"
    content = request.form.get("content", "").strip()
    password = request.form.get("password", "").strip()
    redirect_url = request.form.get("redirect_url", "/")

    if not content or len(content) < 2:
        return redirect(redirect_url)

    spam = is_spam("", content)
    pw_hash = hash_password(password) if password else None
    session_token = request.cookies.get("vc_session") or str(uuid.uuid4())

    conn = get_conn()
    c = conn.cursor()
    p = ph()
    c.execute(
        f"""INSERT INTO comments
            (created_at, post_id, project_id, author_name, password_hash,
             session_token, ip_address, content, is_spam)
            VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p})""",
        (
            datetime.now().isoformat(), post_id, project_id, author,
            pw_hash, session_token, ip, content, 1 if spam else 0,
        ),
    )
    conn.commit()
    conn.close()
    record_action(ip, "comment")

    resp = make_response(redirect(redirect_url))
    resp.set_cookie("vc_session", session_token, max_age=60*60*24*365, httponly=True, samesite="Lax")
    return resp


@app.route("/comment/<int:comment_id>/delete", methods=["POST"])
def delete_comment(comment_id):
    conn = get_conn()
    c = conn.cursor()
    p = ph()

    c.execute(f"SELECT * FROM comments WHERE id={p}", (comment_id,))
    comment = fetchone(c)
    if not comment:
        conn.close(); abort(404)

    session_token = request.cookies.get("vc_session", "")
    password = request.form.get("password", "")
    redirect_url = request.form.get("redirect_url", "/")

    can_delete = (
        (session_token and session_token == comment.get("session_token")) or
        check_password(password, comment.get("password_hash") or "")
    )

    if can_delete:
        c.execute(f"UPDATE comments SET is_deleted=1 WHERE id={p}", (comment_id,))
        conn.commit()

    conn.close()
    return redirect(redirect_url)


# ──────────────────────────────────────────────────────────
# 방문자 통계 기록
# ──────────────────────────────────────────────────────────
import hashlib as _hl

def record_pageview(path: str):
    """페이지뷰 기록 (IP는 해시 처리, 개인정보 보호)"""
    try:
        ip = get_client_ip()
        ip_hash = _hl.md5(ip.encode()).hexdigest()[:12]  # 비식별화
        ua = request.headers.get("User-Agent", "")[:200]
        ref = request.headers.get("Referer", "")[:200]
        # Accept-Language로 국가 힌트
        al = request.headers.get("Accept-Language", "")
        country_hint = al.split(",")[0].split(";")[0].strip()[:10] if al else ""
        conn = get_conn()
        c = conn.cursor()
        p = ph()
        c.execute(
            f"INSERT INTO page_views (created_at, path, ip_hash, referrer, user_agent, country_hint) VALUES ({p},{p},{p},{p},{p},{p})",
            (datetime.now().isoformat(), path, ip_hash, ref, ua, country_hint)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # 통계 실패해도 페이지는 정상 동작


# ──────────────────────────────────────────────────────────
# 관리자 대시보드 /admin
# ──────────────────────────────────────────────────────────
ADMIN_KEY = os.environ.get("ADMIN_KEY", "vibecoder-admin-2026")

@app.route("/admin")
def admin_dashboard():
    if request.args.get("key") != ADMIN_KEY:
        return "401 Unauthorized", 401

    conn = get_conn()
    c = conn.cursor()
    p = ph()

    # 총 방문자 (unique ip_hash 기준)
    c.execute("SELECT COUNT(*) as cnt FROM page_views")
    total_pv = fetchone(c)["cnt"]

    c.execute("SELECT COUNT(DISTINCT ip_hash) as cnt FROM page_views")
    unique_visitors = fetchone(c)["cnt"]

    # 오늘 방문자
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute(f"SELECT COUNT(*) as cnt FROM page_views WHERE created_at LIKE {p}", (f"{today}%",))
    today_pv = fetchone(c)["cnt"]

    c.execute(f"SELECT COUNT(DISTINCT ip_hash) as cnt FROM page_views WHERE created_at LIKE {p}", (f"{today}%",))
    today_uv = fetchone(c)["cnt"]

    # 최근 7일 일별 방문
    daily = []
    for i in range(6, -1, -1):
        from datetime import timedelta
        d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        c.execute(f"SELECT COUNT(*) as cnt FROM page_views WHERE created_at LIKE {p}", (f"{d}%",))
        daily.append({"date": d, "pv": fetchone(c)["cnt"]})

    # 인기 페이지 TOP 10
    c.execute("SELECT path, COUNT(*) as cnt FROM page_views GROUP BY path ORDER BY cnt DESC LIMIT 10")
    top_pages = fetchall(c)

    # 유입 경로 TOP 5
    c.execute("SELECT referrer, COUNT(*) as cnt FROM page_views WHERE referrer != '' GROUP BY referrer ORDER BY cnt DESC LIMIT 5")
    top_refs = fetchall(c)

    # 국가별 (Accept-Language 기반)
    c.execute("SELECT country_hint, COUNT(*) as cnt FROM page_views WHERE country_hint != '' GROUP BY country_hint ORDER BY cnt DESC LIMIT 8")
    top_countries = fetchall(c)

    # 콘텐츠 통계
    c.execute("SELECT COUNT(*) as cnt FROM projects")
    proj_cnt = fetchone(c)["cnt"]
    c.execute("SELECT COUNT(*) as cnt FROM posts WHERE is_deleted=0 AND is_spam=0")
    post_cnt = fetchone(c)["cnt"]
    c.execute("SELECT COUNT(*) as cnt FROM comments WHERE is_deleted=0")
    comment_cnt = fetchone(c)["cnt"]

    conn.close()

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>VibeCoder 관리자 대시보드</title>
<style>
  body{{font-family:system-ui,sans-serif;background:#050508;color:#f1f5f9;margin:0;padding:24px}}
  h1{{color:#a78bfa;margin-bottom:8px}}
  .sub{{color:#64748b;font-size:.85rem;margin-bottom:32px}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;margin-bottom:32px}}
  .card{{background:#0d0d14;border:1px solid rgba(255,255,255,.06);border-radius:12px;padding:20px}}
  .card .num{{font-size:2rem;font-weight:800;background:linear-gradient(135deg,#7c3aed,#06b6d4);-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
  .card .label{{font-size:.8rem;color:#64748b;margin-top:4px}}
  table{{width:100%;border-collapse:collapse;background:#0d0d14;border-radius:12px;overflow:hidden}}
  th{{background:#13131e;padding:10px 14px;text-align:left;font-size:.8rem;color:#64748b}}
  td{{padding:10px 14px;border-top:1px solid rgba(255,255,255,.04);font-size:.88rem}}
  .section{{margin-bottom:32px}}
  h2{{font-size:1rem;color:#a78bfa;margin-bottom:12px}}
  .bar-wrap{{background:#13131e;border-radius:4px;height:8px;margin-top:4px}}
  .bar{{background:linear-gradient(90deg,#7c3aed,#06b6d4);height:8px;border-radius:4px}}
  a{{color:#06b6d4}}
</style>
</head>
<body>
<h1>⚡ VibeCoder 관리자</h1>
<div class="sub">방문자 통계 대시보드 · 오늘 {today}</div>

<div class="grid">
  <div class="card"><div class="num">{today_uv}</div><div class="label">오늘 순방문자</div></div>
  <div class="card"><div class="num">{today_pv}</div><div class="label">오늘 페이지뷰</div></div>
  <div class="card"><div class="num">{unique_visitors}</div><div class="label">누적 순방문자</div></div>
  <div class="card"><div class="num">{total_pv}</div><div class="label">누적 페이지뷰</div></div>
  <div class="card"><div class="num">{proj_cnt}</div><div class="label">등록 프로젝트</div></div>
  <div class="card"><div class="num">{post_cnt}</div><div class="label">라운지 글</div></div>
  <div class="card"><div class="num">{comment_cnt}</div><div class="label">댓글</div></div>
</div>

<div class="section">
  <h2>📅 최근 7일 일별 페이지뷰</h2>
  <table><tr>{''.join(f'<th>{d["date"][5:]}</th>' for d in daily)}</tr>
  <tr>{''.join(f'<td>{d["pv"]}</td>' for d in daily)}</tr></table>
</div>

<div class="section">
  <h2>📄 인기 페이지 TOP 10</h2>
  <table><tr><th>경로</th><th>조회수</th></tr>
  {''.join(f'<tr><td>{r["path"]}</td><td>{r["cnt"]}</td></tr>' for r in top_pages)}
  </table>
</div>

<div class="section">
  <h2>🌍 언어/국가별 방문</h2>
  <table><tr><th>언어</th><th>방문수</th></tr>
  {''.join(f'<tr><td>{r["country_hint"]}</td><td>{r["cnt"]}</td></tr>' for r in top_countries)}
  </table>
</div>

<div class="section">
  <h2>🔗 유입 경로 TOP 5</h2>
  <table><tr><th>Referrer</th><th>수</th></tr>
  {''.join(f'<tr><td style="word-break:break-all;max-width:400px">{r["referrer"][:80]}</td><td>{r["cnt"]}</td></tr>' for r in top_refs)}
  </table>
</div>

<p style="color:#64748b;font-size:.8rem">IP는 MD5 해시로 비식별화 저장됩니다.</p>
</body></html>"""
    return html


# ──────────────────────────────────────────────────────────
# 툴 허브
# ──────────────────────────────────────────────────────────
@app.route("/tools")
def tools():
    record_pageview("/tools")
    return render_template("tools.html")


# ──────────────────────────────────────────────────────────
# API
# ──────────────────────────────────────────────────────────
@app.route("/api/projects")
def api_projects():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id,title,slug,description,tech_stack,demo_url,author,view_count,likes,created_at FROM projects ORDER BY created_at DESC LIMIT 20")
    projects = fetchall(c)
    conn.close()
    for proj in projects:
        if proj.get("tech_stack"):
            try:
                proj["tech_stack"] = json.loads(proj["tech_stack"])
            except Exception:
                pass
    return jsonify(projects)


@app.route("/api/stats")
def api_stats():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM projects")
    pc = fetchone(c)["cnt"]
    c.execute("SELECT COUNT(*) as cnt FROM posts WHERE is_spam=0 AND is_deleted=0")
    lc = fetchone(c)["cnt"]
    c.execute("SELECT SUM(view_count) as total FROM projects")
    vc = fetchone(c)["total"] or 0
    conn.close()
    return jsonify({"projects": pc, "posts": lc, "total_views": vc})


# ──────────────────────────────────────────────────────────
# 에러 핸들러
# ──────────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "서버 오류"}), 500


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5001)
