import os, json, time, hashlib, uuid, re
from flask import Flask, request, jsonify
import requests as req_lib

app = Flask(__name__)

# ── CORS ──────────────────────────────────────────────────────────────────
try:
    from flask_cors import CORS
    CORS(app, origins="*")
except ImportError:
    @app.after_request
    def add_cors(resp):
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
        resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
        return resp

@app.route('/', defaults={'path': ''}, methods=['OPTIONS'])
@app.route('/<path:path>', methods=['OPTIONS'])
def preflight(path):
    from flask import Response
    r = Response()
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    r.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return r, 204

# ── Constants ─────────────────────────────────────────────────────────────
CLIENT_ID      = "YUMx5nI8ZU8Ap8pm"
CLIENT_SECRET  = "dbw2OtmVEeuUvIptb1Coyg"
CLIENT_VERSION = "2.0.0"
PACKAGE_NAME   = "mypikpak.com"
ALGORITHMS = [
    "C9qPpZLN8ucRTaTiUMWYS9cQvWOE", "+r6CQVxjzJV6LCV", "F", "pFJRC",
    "9WXYIDGrwTCz2OiVlgZa90qpECPD6olt", "/750aCr4lm/Sly/c", "RB+DT/gZCrbV", "",
    "CyLsf7hdkIRxRm215hl", "7xHvLi2tOYP0Y92b", "ZGTXXxu8E/MIWaEDB+Sm/",
    "1UI3", "E7fP5Pfijd+7K+t6Tg/NhuLq0eEUVChpJSkrKxpO",
    "ihtqpG6FMt65+Xk+tWUH2", "NhXXU9rg4XXdzo7u5o",
]
API_USER  = "https://user.mypikpak.net"
API_DRIVE = "https://api-drive.mypikpak.net"

TMPDIR = os.environ.get("TMPDIR", "/tmp")

# ── Device ID ─────────────────────────────────────────────────────────────
def get_device_id():
    path = os.path.join(TMPDIR, "pikpak_device.json")
    try:
        with open(path) as f:
            return json.load(f)["device_id"]
    except Exception:
        did = uuid.uuid4().hex[:32]
        with open(path, "w") as f:
            json.dump({"device_id": did}, f)
        return did

SERVER_DEVICE_ID = get_device_id()

# ── Captcha sign ──────────────────────────────────────────────────────────
def make_captcha_sign(device_id=None):
    did = device_id or SERVER_DEVICE_ID
    ts = str(int(time.time() * 1000))
    s = f"{CLIENT_ID}{CLIENT_VERSION}{PACKAGE_NAME}{did}{ts}"
    for alg in ALGORITHMS:
        s = hashlib.md5((s + alg).encode()).hexdigest()
    return ts, "1." + s

# ── Captcha init ──────────────────────────────────────────────────────────
def captcha_init(action, device_id=None, user_id="", captcha_token="", meta_extra=None):
    did = device_id or SERVER_DEVICE_ID
    ts, sign = make_captcha_sign(did)
    meta = {
        "client_version": CLIENT_VERSION,
        "package_name": PACKAGE_NAME,
        "user_id": user_id or "",
        "timestamp": ts,
        "captcha_sign": sign,
    }
    if meta_extra:
        meta.update(meta_extra)
    body = {
        "action": action,
        "captcha_token": captcha_token or "",
        "client_id": CLIENT_ID,
        "device_id": did,
        "meta": meta,
        "redirect_uri": "xlaccsdk01://xbase.cloud/callback?state=harbor",
    }
    try:
        r = req_lib.post(
            f"{API_USER}/v1/shield/captcha/init",
            json=body,
            params={"client_id": CLIENT_ID},
            headers={"User-Agent": "Mozilla/5.0", "X-Device-ID": did},
            timeout=15,
        )
        d = r.json()
        return d.get("captcha_token", ""), d.get("url", "")
    except Exception:
        return "", ""

def captcha_init_for_login(username, device_id=None):
    did = device_id or SERVER_DEVICE_ID
    metas = {}
    if re.match(r"\S+@\S+\.\S+", username):
        metas["email"] = username
    elif 11 <= len(username) <= 18:
        metas["phone_number"] = username
    else:
        metas["username"] = username
    body = {
        "action": "POST:/v1/auth/signin",
        "captcha_token": "",
        "client_id": CLIENT_ID,
        "device_id": did,
        "meta": metas,
        "redirect_uri": "xlaccsdk01://xbase.cloud/callback?state=harbor",
    }
    try:
        r = req_lib.post(
            f"{API_USER}/v1/shield/captcha/init",
            json=body,
            params={"client_id": CLIENT_ID},
            headers={"User-Agent": "Mozilla/5.0", "X-Device-ID": did},
            timeout=15,
        )
        d = r.json()
        return d.get("captcha_token", ""), d.get("url", "")
    except Exception:
        return "", ""

# ── Token store ───────────────────────────────────────────────────────────
TOKEN_FILE = os.path.join(TMPDIR, "pikpak_tokens.json")

def load_tokens():
    try:
        with open(TOKEN_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def save_tokens(tokens):
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=2)

# ── Auth headers helper ────────────────────────────────────────────────────
def auth_headers(access_token, device_id=None, captcha_token=""):
    did = device_id or SERVER_DEVICE_ID
    return {
        "Authorization": f"Bearer {access_token}",
        "X-Device-ID": did,
        "X-Captcha-Token": captcha_token or "",
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json",
    }

# ── /api/login ─────────────────────────────────────────────────────────────
@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json or {}
    method = data.get("method", "token")
    device_id = data.get("device_id") or SERVER_DEVICE_ID

    if method == "token":
        token = data.get("access_token", "").strip().lstrip("Bearer ").strip().strip('"\'\'\"')
        if not token:
            return jsonify({"error": "Token vazio"}), 400
        ct, _ = captcha_init("GET:/drive/v1/about", device_id=device_id)
        r = req_lib.get(f"{API_DRIVE}/drive/v1/about",
                        headers=auth_headers(token, device_id, ct), timeout=15)
        if r.status_code == 200:
            info = r.json()
            tokens = load_tokens()
            tokens.update({"access_token": token, "user_id": info.get("sub", "")})
            save_tokens(tokens)
            return jsonify({"success": True})
        try:
            err = r.json()
            detail = err.get("error_description") or err.get("error") or str(err)[:200]
        except Exception:
            detail = r.text[:200]
        return jsonify({"error": f"Token inválido: {detail}"}), 401

    if method == "force_token":
        token = data.get("access_token", "").strip().lstrip("Bearer ").strip()
        if not token:
            return jsonify({"error": "Token vazio"}), 400
        tokens = load_tokens()
        tokens["access_token"] = token
        save_tokens(tokens)
        return jsonify({"success": True})

    if method == "password":
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()
        if not username or not password:
            return jsonify({"error": "Email e senha obrigatórios"}), 400
        ct, captcha_url = captcha_init_for_login(username, device_id=device_id)
        if captcha_url:
            return jsonify({"captcha_required": True, "captcha_url": captcha_url, "captcha_token": ct})
        return _do_signin(username, password, ct, device_id)

    if method == "password_with_captcha":
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()
        ct = data.get("captcha_token", "")
        return _do_signin(username, password, ct, device_id)

    if method == "otp":
        # Signin with verification_code
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()
        code = data.get("code", "").strip()
        ct = data.get("captcha_token", "")
        vid = data.get("verification_id", "")
        return _do_signin(username, password, ct, device_id, code=code, verification_id=vid)

    return jsonify({"error": f"Método desconhecido: {method}"}), 400

def _do_signin(username, password, captcha_token, device_id, code=None, verification_id=None):
    body = {
        "captcha_token": captcha_token or "",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "username": username,
        "password": password,
    }
    if code:
        body["verification_code"] = code
    if verification_id:
        body["verification_id"] = verification_id

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
        "X-Device-ID": device_id or SERVER_DEVICE_ID,
        "X-Captcha-Token": captcha_token or "",
    }
    r = req_lib.post(f"{API_USER}/v1/auth/signin?client_id={CLIENT_ID}",
                     json=body, headers=headers, timeout=20)
    if r.status_code == 200:
        resp = r.json()
        tokens = load_tokens()
        tokens.update({
            "access_token":  resp.get("access_token", ""),
            "refresh_token": resp.get("refresh_token", ""),
            "user_id":       resp.get("sub", ""),
        })
        save_tokens(tokens)
        return jsonify({"success": True})

    try:
        err = r.json()
    except Exception:
        return jsonify({"error": f"HTTP {r.status_code}: {r.text[:200]}"}), r.status_code

    # Needs email verification?
    error_code = err.get("error_code")
    desc = err.get("error_description") or err.get("error") or f"HTTP {r.status_code}"
    needs_otp = (
        error_code == 4002
        or "verification" in desc.lower()
        or "verify" in desc.lower()
        or err.get("verification_id")
    )
    if needs_otp:
        vid = err.get("verification_id", "")
        # Send the verification email if we have a verification_id
        if vid:
            try:
                req_lib.post(
                    f"{API_USER}/v1/auth/2fa/token",
                    json={"verification_id": vid},
                    headers=headers,
                    timeout=10,
                )
            except Exception:
                pass
        return jsonify({
            "otp_required": True,
            "verification_id": vid,
            "captcha_token": captcha_token,
            "message": "Código enviado para o seu e-mail.",
        })

    return jsonify({"error": desc}), r.status_code

# ── /api/auto-login ────────────────────────────────────────────────────────
@app.route("/api/auto-login", methods=["POST"])
def api_auto_login():
    data = request.json or {}
    device_id = data.get("device_id") or SERVER_DEVICE_ID
    tokens = load_tokens()
    refresh = tokens.get("refresh_token", "")
    if not refresh:
        return jsonify({"error": "Sem refresh token"}), 401
    body = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh,
    }
    r = req_lib.post(f"{API_USER}/v1/auth/token?client_id={CLIENT_ID}", json=body,
                     headers={"User-Agent": "Mozilla/5.0", "X-Device-ID": device_id},
                     timeout=15)
    if r.status_code == 200:
        resp = r.json()
        tokens["access_token"]  = resp.get("access_token", "")
        tokens["refresh_token"] = resp.get("refresh_token", refresh)
        tokens["user_id"]       = resp.get("sub", tokens.get("user_id", ""))
        save_tokens(tokens)
        return jsonify({"success": True, "access_token": tokens["access_token"]})
    return jsonify({"error": "Refresh falhou"}), 401

# ── /api/files ─────────────────────────────────────────────────────────────
@app.route("/api/files", methods=["GET"])
def api_files():
    tokens = load_tokens()
    access = tokens.get("access_token", "")
    if not access:
        return jsonify({"error": "Não autenticado"}), 401
    parent_id = request.args.get("parent_id", "")
    page_token = request.args.get("page_token", "")
    ct, _ = captcha_init("GET:/drive/v1/files", user_id=tokens.get("user_id", ""))
    params = {
        "parent_id": parent_id or "",
        "thumbnail_size": "SIZE_MEDIUM",
        "with_audit": "false",
        "limit": "100",
        "filters": '{"phase":{"eq":"PHASE_TYPE_COMPLETE"},"trashed":{"eq":false}}',
    }
    if page_token:
        params["page_token"] = page_token
    r = req_lib.get(f"{API_DRIVE}/drive/v1/files", params=params,
                    headers=auth_headers(access, captcha_token=ct), timeout=20)
    if r.status_code == 200:
        return jsonify(r.json()), 200
    return jsonify({"error": f"HTTP {r.status_code}"}), r.status_code

# ── /api/file-link ─────────────────────────────────────────────────────────
@app.route("/api/file-link", methods=["GET"])
def api_file_link():
    tokens = load_tokens()
    access = tokens.get("access_token", "")
    if not access:
        return jsonify({"error": "Não autenticado"}), 401
    file_id = request.args.get("file_id", "")
    if not file_id:
        return jsonify({"error": "file_id obrigatório"}), 400
    ct, _ = captcha_init(f"GET:/drive/v1/files/{file_id}", user_id=tokens.get("user_id", ""))
    r = req_lib.get(f"{API_DRIVE}/drive/v1/files/{file_id}",
                    headers=auth_headers(access, captcha_token=ct), timeout=15)
    if r.status_code == 200:
        return jsonify(r.json()), 200
    return jsonify({"error": f"HTTP {r.status_code}"}), r.status_code

# ── /api/share ─────────────────────────────────────────────────────────────
@app.route("/api/share", methods=["POST"])
def api_share():
    data = request.json or {}
    share_url = data.get("url", "")
    passcode = data.get("passcode", "")
    tokens = load_tokens()
    access = tokens.get("access_token", "")
    if not access:
        return jsonify({"error": "Não autenticado"}), 401

    # Extract share ID
    m = re.search(r"/s/([A-Za-z0-9_-]+)", share_url)
    if not m:
        m = re.search(r"share_id=([A-Za-z0-9_-]+)", share_url)
    if not m:
        return jsonify({"error": "URL de compartilhamento inválida"}), 400
    share_id = m.group(1)

    ct, _ = captcha_init("GET:/drive/v1/share", user_id=tokens.get("user_id", ""))
    params = {"share_id": share_id}
    if passcode:
        params["pass_code"] = passcode
    r = req_lib.get(f"{API_DRIVE}/drive/v1/share",
                    params=params, headers=auth_headers(access, captcha_token=ct), timeout=15)
    if r.status_code != 200:
        return jsonify({"error": f"HTTP {r.status_code}"}), r.status_code
    share_info = r.json()
    share_token = share_info.get("share_token", "")
    files_data = share_info.get("files", [])

    results = []
    for f in files_data:
        results.append({
            "id": f.get("id", ""),
            "name": f.get("name", ""),
            "size": f.get("size", 0),
            "mime": f.get("mime_type", ""),
            "kind": f.get("kind", ""),
            "links": f.get("medias", []),
        })

    return jsonify({"share_id": share_id, "share_token": share_token, "files": results})

# ── /api/share-links ───────────────────────────────────────────────────────
@app.route("/api/share-links", methods=["POST"])
def api_share_links():
    data = request.json or {}
    share_id = data.get("share_id", "")
    share_token = data.get("share_token", "")
    file_id = data.get("file_id", "")
    tokens = load_tokens()
    access = tokens.get("access_token", "")
    if not access:
        return jsonify({"error": "Não autenticado"}), 401

    ct, _ = captcha_init(f"GET:/drive/v1/files/{file_id}", user_id=tokens.get("user_id", ""))
    headers = auth_headers(access, captcha_token=ct)
    headers["X-Share-Token"] = share_token
    r = req_lib.get(f"{API_DRIVE}/drive/v1/files/{file_id}",
                    params={"share_id": share_id}, headers=headers, timeout=15)
    if r.status_code == 200:
        return jsonify(r.json()), 200
    return jsonify({"error": f"HTTP {r.status_code}"}), r.status_code

# ── /api/proxy ─────────────────────────────────────────────────────────────
@app.route("/api/proxy", methods=["POST"])
def api_proxy():
    data = request.json or {}
    url = data.get("url", "")
    method = data.get("method", "GET").upper()
    headers = data.get("headers", {})
    body = data.get("body")
    if not url:
        return jsonify({"error": "URL vazia"}), 400
    from urllib.parse import urlparse as _up
    host = _up(url).netloc.lower()
    allowed = ["mypikpak.net", "mypikpak.com", "dropboxapi.com", "dropbox.com", "content.dropboxapi.com"]
    if not any(a in host for a in allowed):
        return jsonify({"error": f"Domínio não permitido: {host}"}), 403
    for h in ["host", "content-length", "transfer-encoding", "connection"]:
        headers.pop(h, None); headers.pop(h.title(), None)
    try:
        if isinstance(body, str):
            r = req_lib.request(method, url, data=body.encode(), headers=headers, timeout=30)
        elif body:
            r = req_lib.request(method, url, json=body, headers=headers, timeout=30)
        else:
            r = req_lib.request(method, url, headers=headers, timeout=30)
        try:
            return jsonify(r.json()), r.status_code
        except Exception:
            return r.text, r.status_code, {"Content-Type": r.headers.get("Content-Type", "text/plain")}
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── /api/dropbox-test ──────────────────────────────────────────────────────
@app.route("/api/dropbox-test", methods=["POST"])
def api_dropbox_test():
    token = (request.json or {}).get("token", "")
    if not token:
        return jsonify({"error": "Token vazio"}), 400
    r = req_lib.post("https://api.dropboxapi.com/2/users/get_current_account",
                     headers={"Authorization": f"Bearer {token}"}, timeout=10)
    if r.status_code == 200:
        info = r.json()
        return jsonify({"success": True, "name": info.get("name", {}).get("display_name", "")})
    return jsonify({"error": f"HTTP {r.status_code}"}), r.status_code

# ── /api/dropbox-send ──────────────────────────────────────────────────────
@app.route("/api/dropbox-send", methods=["POST"])
def api_dropbox_send():
    data = request.json or {}
    token = data.get("token", "")
    folder = data.get("folder", "/PikPak").rstrip("/")
    url = data.get("url", "")
    name = data.get("name", "file")
    if not token or not url:
        return jsonify({"error": "token e url obrigatórios"}), 400
    # Download
    try:
        dl = req_lib.get(url, timeout=60, stream=True)
        dl.raise_for_status()
        content = dl.content
    except Exception as e:
        return jsonify({"error": f"Download falhou: {e}"}), 500
    # Upload to Dropbox
    dest = f"{folder}/{name}"
    r = req_lib.post(
        "https://content.dropboxapi.com/2/files/upload",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
            "Dropbox-API-Arg": json.dumps({"path": dest, "mode": "overwrite", "autorename": True}),
        },
        data=content,
        timeout=120,
    )
    if r.status_code in (200, 201):
        return jsonify({"success": True, "path": dest})
    return jsonify({"error": f"Upload falhou: HTTP {r.status_code}"}), r.status_code

# ── / ──────────────────────────────────────────────────────────────────────
GITHUB_RAW = "https://raw.githubusercontent.com/fypak-ai/pikpak-manager-v2/main/index.html"
_cache = {"html": None, "ts": 0}

@app.route("/")
def index():
    now = time.time()
    if _cache["html"] and now - _cache["ts"] < 300:
        return _cache["html"]
    try:
        import urllib.request as _ur
        with _ur.urlopen(GITHUB_RAW, timeout=8) as resp:
            html = resp.read().decode("utf-8")
            _cache["html"] = html
            _cache["ts"] = now
            return html
    except Exception:
        pass
    for fname in ["index.html"]:
        fpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
        if os.path.exists(fpath):
            with open(fpath, encoding="utf-8") as f:
                return f.read()
    return "<h1>PikPak Manager v2</h1>"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
