"""
Muhii — backend with admin panel support.
Deploy this on Render.com (free tier) — see README-ADMIN.md for phone-only steps.
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3, os, datetime, uuid, urllib.request, urllib.parse, json

app = Flask(__name__)
CORS(app)  # allow the GitHub Pages site to call this API

DB_PATH = os.path.join(os.path.dirname(__file__), "muhii.db")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change-me")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")  # optional
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")      # optional

def notify_telegram(req_data, req_id):
    """Send a Telegram message when a new request arrives. Silently does
    nothing if TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID aren't set."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    text = (
        f"🆕 Gaaffii Haaraa (#{req_id})\n"
        f"👤 {req_data.get('full_name')}\n"
        f"📞 {req_data.get('contact')}\n"
        f"📱 {req_data.get('platform')}\n"
        f"📝 {req_data.get('issue')}"
    )
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = urllib.parse.urlencode({"chat_id": TELEGRAM_CHAT_ID, "text": text}).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=payload), timeout=5)
    except Exception:
        pass  # never let a notification failure break the request submission

def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            contact TEXT NOT NULL,
            platform TEXT NOT NULL,
            issue TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'new'
        )
    """)
    con.commit()
    con.close()

init_db()

def check_admin(req):
    return req.headers.get("X-Admin-Password") == ADMIN_PASSWORD

@app.get("/")
def health():
    return jsonify({"status": "ok", "service": "muhii-backend"})

@app.post("/api/requests")
def create_request():
    data = request.get_json(force=True) or {}
    required = ["full_name", "contact", "platform", "issue"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"missing fields: {', '.join(missing)}"}), 400

    # Safety: never accept or store credential-like fields even if sent by mistake.
    for bad_key in ("password", "pin", "otp", "code", "login_password"):
        data.pop(bad_key, None)

    req_id = str(uuid.uuid4())[:8]
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "INSERT INTO requests (id, full_name, contact, platform, issue, created_at) VALUES (?,?,?,?,?,?)",
        (req_id, data["full_name"], data["contact"], data["platform"], data["issue"],
         datetime.datetime.utcnow().isoformat())
    )
    con.commit()
    con.close()
    notify_telegram(data, req_id)
    return jsonify({"request_id": req_id}), 201

@app.get("/api/admin/requests")
def list_requests():
    if not check_admin(request):
        return jsonify({"error": "unauthorized"}), 401
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM requests ORDER BY created_at DESC")]
    con.close()
    return jsonify(rows)

@app.post("/api/admin/requests/<req_id>/status")
def update_status(req_id):
    if not check_admin(request):
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(force=True) or {}
    new_status = data.get("status")
    if new_status not in ("new", "in_progress", "done"):
        return jsonify({"error": "invalid status"}), 400
    con = sqlite3.connect(DB_PATH)
    con.execute("UPDATE requests SET status=? WHERE id=?", (new_status, req_id))
    con.commit()
    con.close()
    return jsonify({"ok": True})

@app.delete("/api/admin/requests/<req_id>")
def delete_request(req_id):
    if not check_admin(request):
        return jsonify({"error": "unauthorized"}), 401
    con = sqlite3.connect(DB_PATH)
    con.execute("DELETE FROM requests WHERE id=?", (req_id,))
    con.commit()
    con.close()
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(debug=True)
