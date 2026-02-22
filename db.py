"""VibeCoder DB 모듈 — PostgreSQL / SQLite 통합
익명 작성자 + 세션 식별 + 스팸 방지 스키마
"""

import os
import sqlite3

DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_POSTGRES = bool(DATABASE_URL)


def get_conn():
    if USE_POSTGRES:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        conn = sqlite3.connect(
            os.path.join(os.path.dirname(__file__), "vibecoder.db"),
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        return conn


def ph():
    return "%s" if USE_POSTGRES else "?"


def fetchall(cursor):
    rows = cursor.fetchall()
    if USE_POSTGRES:
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, r)) for r in rows]
    return [dict(r) for r in rows]


def fetchone(cursor):
    row = cursor.fetchone()
    if row is None:
        return None
    if USE_POSTGRES:
        cols = [d[0] for d in cursor.description]
        return dict(zip(cols, row))
    return dict(row)


def init_db():
    conn = get_conn()
    c = conn.cursor()
    S = "SERIAL" if USE_POSTGRES else "INTEGER"
    PK = "SERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"

    # ── 프로젝트 테이블 ──
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS projects (
            id {PK},
            created_at TEXT NOT NULL,
            title TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            description TEXT,
            tech_stack TEXT,
            demo_url TEXT,
            github_url TEXT,
            thumbnail TEXT,
            author TEXT DEFAULT '익명코더',
            is_featured INTEGER DEFAULT 0,
            view_count INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            ip_address TEXT
        )
    """)

    # ── 게시글 테이블 (Lounge) — 익명 작성 지원 ──
    # author_name: 닉네임 (자유 입력)
    # password_hash: 익명글 수정/삭제용 간단 해시 (sha256)
    # ip_address: 스팸 방지용 IP (로깅 전용, 노출 안 함)
    # session_token: 브라우저 쿠키 기반 식별자 (본인 글 수정 허용)
    # is_spam: AI/룰 기반 스팸 분류 플래그
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS posts (
            id {PK},
            created_at TEXT NOT NULL,
            title TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            content TEXT,
            category TEXT DEFAULT 'free',
            author_name TEXT DEFAULT '익명코더',
            password_hash TEXT,
            session_token TEXT,
            ip_address TEXT,
            tags TEXT,
            view_count INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            is_spam INTEGER DEFAULT 0,
            is_deleted INTEGER DEFAULT 0
        )
    """)

    # ── 댓글 테이블 ──
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS comments (
            id {PK},
            created_at TEXT NOT NULL,
            post_id INTEGER,
            project_id INTEGER,
            author_name TEXT DEFAULT '익명코더',
            password_hash TEXT,
            session_token TEXT,
            ip_address TEXT,
            content TEXT NOT NULL,
            is_approved INTEGER DEFAULT 1,
            is_spam INTEGER DEFAULT 0,
            is_deleted INTEGER DEFAULT 0
        )
    """)

    # ── IP 속도 제한 테이블 (Flask-Limiter 없이 직접 구현) ──
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS rate_limits (
            id {PK},
            ip_address TEXT NOT NULL,
            action TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # ── 방문자 통계 테이블 ──
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS page_views (
            id {PK},
            created_at TEXT NOT NULL,
            path TEXT NOT NULL,
            ip_hash TEXT,
            referrer TEXT,
            user_agent TEXT,
            country_hint TEXT
        )
    """)

    conn.commit()
    conn.close()
    print(f"DB 초기화 완료 ({'PostgreSQL' if USE_POSTGRES else 'SQLite'})")
