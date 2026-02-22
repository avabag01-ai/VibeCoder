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
import hashlib
from datetime import datetime, timedelta
from flask import (
    Flask, render_template, request, redirect,
    url_for, jsonify, abort, make_response
)
from dotenv import load_dotenv

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
    """간단 sha256 해시 (bcrypt 없이 경량으로)"""
    return hashlib.sha256(raw.encode()).hexdigest()


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

    return render_template("index.html",
        featured=featured,
        latest_posts=latest_posts,
        project_count=project_count,
        post_count=post_count,
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

    return render_template("showcase.html",
        projects=projects,
        page=page,
        total_pages=(total + per_page - 1) // per_page,
        total=total,
    )


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
    pw_hash = hash_password(password) if password else None

    can_delete = (
        (session_token and session_token == post.get("session_token")) or
        (pw_hash and pw_hash == post.get("password_hash"))
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
    pw_hash = hash_password(password) if password else None
    redirect_url = request.form.get("redirect_url", "/")

    can_delete = (
        (session_token and session_token == comment.get("session_token")) or
        (pw_hash and pw_hash == comment.get("password_hash"))
    )

    if can_delete:
        c.execute(f"UPDATE comments SET is_deleted=1 WHERE id={p}", (comment_id,))
        conn.commit()

    conn.close()
    return redirect(redirect_url)


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
