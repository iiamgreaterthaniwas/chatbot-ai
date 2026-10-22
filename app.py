from flask import Flask, request, jsonify, render_template, Response, stream_with_context, g, session, redirect
from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.fernet import Fernet, InvalidToken
from openai import OpenAI
from dotenv import load_dotenv
from contextlib import contextmanager
from datetime import timedelta
from functools import wraps
import threading
import pymysql
import hashlib
import base64
import json
import re
import os

load_dotenv()

app = Flask(__name__)

# 用于给登录 session 签名，多进程部署时每个进程必须一致，所以必须在 .env 里配置
app.secret_key = os.environ.get("SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("未配置 SECRET_KEY 环境变量，请在 .env 中设置一个随机字符串")
app.permanent_session_lifetime = timedelta(days=30)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# 部署到 HTTPS 后设为 1，登录 cookie 只通过 HTTPS 传输
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE") == "1"

MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
SYSTEM_PROMPT = os.environ.get(
    "SYSTEM_PROMPT",
    "你是「饺子」🥟，一个专业、友好的 AI 助手。请用清晰的结构回答问题，适当使用 Markdown（标题、列表、代码块、表格）。"
)
USERNAME_RE = re.compile(r"^[A-Za-z0-9_一-龥]{3,20}$")

DB_CONFIG = {
    "host": os.environ.get("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.environ.get("MYSQL_PORT", 3306)),
    "user": os.environ.get("MYSQL_USER", "root"),
    "password": os.environ.get("MYSQL_PASSWORD", ""),
    "database": os.environ.get("MYSQL_DATABASE", "chatbot"),
}

DEEPSEEK_BASE_URL = "https://api.deepseek.com"


def make_client(api_key):
    """每个用户用自己的 API Key"""
    return OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)


# ---------- API Key 加密 ----------
# 用户的 API Key 加密后存进数据库，密钥由 SECRET_KEY 派生（修改 SECRET_KEY 后已保存的 Key 会失效，需要用户重新填写）
_fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(app.secret_key.encode()).digest()))


def encrypt_api_key(api_key):
    return _fernet.encrypt(api_key.encode()).decode()


def decrypt_api_key(token):
    if not token:
        return None
    try:
        return _fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        return None


def mask_api_key(api_key):
    return api_key[:5] + "…" + api_key[-4:] if len(api_key) > 12 else "已设置"


# ---------- 数据库 ----------

@contextmanager
def db():
    """打开一个连接并返回游标，正常结束自动提交，出错自动回滚"""
    conn = pymysql.connect(**DB_CONFIG, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users (
        id             INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        username       VARCHAR(20) NOT NULL UNIQUE,
        password_hash  VARCHAR(255) NOT NULL,
        api_key        VARCHAR(512) NULL COMMENT '用户自己的 DeepSeek API Key（加密存储）',
        created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表'""",
    """CREATE TABLE IF NOT EXISTS conversations (
        id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        user_id     INT UNSIGNED NOT NULL,
        title       VARCHAR(100) NOT NULL,
        created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_user_updated (user_id, updated_at),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='对话表'""",
    """CREATE TABLE IF NOT EXISTS messages (
        id               INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        conversation_id  INT UNSIGNED NOT NULL,
        role             ENUM('user', 'assistant') NOT NULL,
        content          MEDIUMTEXT NOT NULL,
        reasoning        MEDIUMTEXT NULL COMMENT '推理模型的思考过程',
        created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_conversation (conversation_id, id),
        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='对话记录表'""",
]

_db_ready = False
_db_lock = threading.Lock()


@app.before_request
def init_db():
    """第一次请求时自动建表（库本身需要提前建好）"""
    global _db_ready
    if _db_ready:
        return
    with _db_lock:
        if not _db_ready:
            with db() as cur:
                for sql in SCHEMA:
                    cur.execute(sql)
                # 旧版 users 表没有 api_key 字段，自动补上
                cur.execute(
                    "SELECT COUNT(*) AS n FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'api_key'"
                )
                if cur.fetchone()["n"] == 0:
                    cur.execute(
                        "ALTER TABLE users ADD COLUMN api_key VARCHAR(512) NULL "
                        "COMMENT '用户自己的 DeepSeek API Key（加密存储）' AFTER password_hash"
                    )
            _db_ready = True


# ---------- 用户 ----------

def load_user():
    """从 session 读取当前登录用户，用户已被删除时清掉 session"""
    if "user" not in g:
        g.user = None
        user_id = session.get("user_id")
        if user_id:
            with db() as cur:
                cur.execute("SELECT id, username, api_key FROM users WHERE id = %s", (user_id,))
                g.user = cur.fetchone()
            if g.user is None:
                session.clear()
    return g.user


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if load_user() is None:
            return jsonify({"error": "请先登录"}), 401
        return view(*args, **kwargs)
    return wrapper


def current_user_id():
    return g.user["id"]


def log_in(user_id):
    session.clear()
    session.permanent = True
    session["user_id"] = user_id


def read_credentials():
    data = request.get_json(silent=True) or {}
    return str(data.get("username") or "").strip(), str(data.get("password") or "")


@app.route('/login')
def login_page():
    if load_user():
        return redirect('/')
    return render_template('login.html')


@app.route('/api/register', methods=['POST'])
def register():
    username, password = read_credentials()
    if not USERNAME_RE.match(username):
        return jsonify({"error": "用户名需为 3-20 位字母、数字、下划线或汉字"}), 400
    if len(password) < 6:
        return jsonify({"error": "密码至少 6 位"}), 400
    try:
        with db() as cur:
            cur.execute(
                "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
                (username, generate_password_hash(password))
            )
            user_id = cur.lastrowid
    except pymysql.err.IntegrityError:
        return jsonify({"error": "用户名已被注册"}), 409
    log_in(user_id)
    return jsonify({"username": username})


@app.route('/api/login', methods=['POST'])
def login():
    username, password = read_credentials()
    with db() as cur:
        cur.execute("SELECT id, username, password_hash FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
    if user is None or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "用户名或密码错误"}), 401
    log_in(user["id"])
    return jsonify({"username": user["username"]})


@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"ok": True})


def get_conversation(cur, conv_id, user_id):
    cur.execute("SELECT id, title FROM conversations WHERE id = %s AND user_id = %s", (conv_id, user_id))
    return cur.fetchone()


# ---------- 页面 & 接口 ----------

@app.route('/')
def index():
    user = load_user()
    if user is None:
        return redirect('/login')
    return render_template(
        'index.html', model=MODEL, username=user["username"],
        has_api_key=decrypt_api_key(user["api_key"]) is not None
    )


@app.route('/api/settings', methods=['GET'])
@login_required
def get_settings():
    api_key = decrypt_api_key(g.user["api_key"])
    # 不把完整的 Key 返回给前端，只返回打码后的
    return jsonify({"has_api_key": api_key is not None, "api_key_masked": mask_api_key(api_key) if api_key else None})


@app.route('/api/settings', methods=['PUT'])
@login_required
def save_settings():
    data = request.get_json(silent=True) or {}
    api_key = str(data.get('api_key') or '').strip()
    if api_key:
        if len(api_key) > 200 or not api_key.isascii() or " " in api_key:
            return jsonify({"error": "API Key 格式不正确"}), 400
        # 用模型列表接口校验 Key 是否可用（不消耗 token）
        try:
            make_client(api_key).models.list()
        except Exception as e:
            return jsonify({"error": "API Key 校验失败：" + str(e)}), 400
    with db() as cur:
        cur.execute(
            "UPDATE users SET api_key = %s WHERE id = %s",
            (encrypt_api_key(api_key) if api_key else None, current_user_id())
        )
    return jsonify({"has_api_key": bool(api_key), "api_key_masked": mask_api_key(api_key) if api_key else None})


@app.route('/api/conversations', methods=['GET'])
@login_required
def list_conversations():
    user_id = current_user_id()
    with db() as cur:
        cur.execute(
            "SELECT id, title FROM conversations WHERE user_id = %s ORDER BY updated_at DESC, id DESC",
            (user_id,)
        )
        rows = cur.fetchall()
    return jsonify(rows)


@app.route('/api/conversations', methods=['DELETE'])
@login_required
def clear_conversations():
    user_id = current_user_id()
    with db() as cur:
        cur.execute("DELETE FROM conversations WHERE user_id = %s", (user_id,))
    return jsonify({"ok": True})


@app.route('/api/conversations/<int:conv_id>', methods=['GET'])
@login_required
def conversation_messages(conv_id):
    user_id = current_user_id()
    with db() as cur:
        conv = get_conversation(cur, conv_id, user_id)
        if conv is None:
            return jsonify({"error": "对话不存在"}), 404
        cur.execute(
            "SELECT role, content, reasoning FROM messages WHERE conversation_id = %s ORDER BY id",
            (conv_id,)
        )
        rows = cur.fetchall()
    return jsonify({"id": conv["id"], "title": conv["title"], "messages": rows})


@app.route('/api/conversations/<int:conv_id>', methods=['DELETE'])
@login_required
def delete_conversation(conv_id):
    user_id = current_user_id()
    with db() as cur:
        cur.execute("DELETE FROM conversations WHERE id = %s AND user_id = %s", (conv_id, user_id))
    return jsonify({"ok": True})


def ndjson(obj):
    return json.dumps(obj, ensure_ascii=False) + "\n"


@app.route('/chat', methods=['POST'])
@login_required
def chat():
    user_id = current_user_id()
    api_key = decrypt_api_key(g.user["api_key"])
    if api_key is None:
        return jsonify({"error": "请先在「API Key 设置」中填写你自己的 DeepSeek API Key", "code": "need_api_key"}), 400
    data = request.get_json(silent=True) or {}
    conv_id = data.get('conversation_id')
    regenerate = bool(data.get('regenerate'))
    user_message = str(data.get('message') or '').strip()

    with db() as cur:
        if conv_id:
            if get_conversation(cur, conv_id, user_id) is None:
                return jsonify({"error": "对话不存在"}), 404
        elif regenerate:
            return jsonify({"error": "缺少对话 ID"}), 400

        if regenerate:
            # 重新生成：删掉最后一条 AI 回复，用最后一条用户消息重新提问
            cur.execute(
                "SELECT id, role, content FROM messages WHERE conversation_id = %s ORDER BY id DESC LIMIT 1",
                (conv_id,)
            )
            last = cur.fetchone()
            if last is None:
                return jsonify({"error": "没有可以重新生成的消息"}), 400
            if last["role"] == "assistant":
                cur.execute("DELETE FROM messages WHERE id = %s", (last["id"],))
                cur.execute(
                    "SELECT content FROM messages WHERE conversation_id = %s AND role = 'user' ORDER BY id DESC LIMIT 1",
                    (conv_id,)
                )
                last = cur.fetchone()
                if last is None:
                    return jsonify({"error": "没有可以重新生成的消息"}), 400
            user_message = last["content"]
        else:
            if not user_message:
                return jsonify({"error": "消息不能为空"}), 400
            if not conv_id:
                cur.execute(
                    "INSERT INTO conversations (user_id, title) VALUES (%s, %s)", (user_id, user_message[:30])
                )
                conv_id = cur.lastrowid
            cur.execute(
                "INSERT INTO messages (conversation_id, role, content) VALUES (%s, 'user', %s)",
                (conv_id, user_message)
            )
        cur.execute("UPDATE conversations SET updated_at = NOW() WHERE id = %s", (conv_id,))

    def generate():
        content, reasoning = [], []
        yield ndjson({"conversation_id": conv_id, "title": user_message[:30]})
        try:
            # 只发送当前这一条消息，不带历史上下文，节省 token
            stream = make_client(api_key).chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message}
                ],
                stream=True
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                # 推理模型会额外返回思考过程
                piece = getattr(delta, "reasoning_content", None)
                if piece:
                    reasoning.append(piece)
                    yield ndjson({"reasoning": piece})
                if delta.content:
                    content.append(delta.content)
                    yield ndjson({"delta": delta.content})
        except Exception as e:
            yield ndjson({"error": str(e)})
        finally:
            # 用户中途停止时也会走到这里，保存已经生成的部分
            if content:
                with db() as cur:
                    cur.execute(
                        "INSERT INTO messages (conversation_id, role, content, reasoning) VALUES (%s, 'assistant', %s, %s)",
                        (conv_id, "".join(content), "".join(reasoning) or None)
                    )

    return Response(
        stream_with_context(generate()),
        mimetype='application/x-ndjson',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
