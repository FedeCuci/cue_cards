import json
import os
import re
import sqlite3
import tempfile
import urllib.error
import urllib.request
from datetime import date, timedelta

from flask import Flask, g, jsonify, request, send_from_directory

BASE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(BASE, "site")
DATA = os.path.join(BASE, "data")
CARDS = os.path.join(SITE, "cards.json")
DB = os.path.join(DATA, "progress.db")
PASSWORD = os.environ.get("EDIT_PASSWORD", "")

# AI "write the missing answers" feature (reuses the OpenRouter key from radar).
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemini-3-flash-preview")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
FILL_MAX = 40  # most cards to answer in one click, to bound the API call

# Leitner boxes: get a card right and it climbs a box and comes back later;
# get it wrong and it drops to box 1. Values are days until the card is due again.
BOX_DAYS = {1: 1, 2: 3, 3: 7, 4: 16, 5: 35}
MAX_BOX = 5

app = Flask(__name__)


def db():
    if "db" not in g:
        os.makedirs(DATA, exist_ok=True)
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
        g.db.execute(
            "CREATE TABLE IF NOT EXISTS review ("
            "front TEXT PRIMARY KEY, box INTEGER NOT NULL, due TEXT NOT NULL, "
            "last TEXT, seen INTEGER NOT NULL DEFAULT 0, "
            "correct INTEGER NOT NULL DEFAULT 0)"
        )
    return g.db


@app.teardown_appcontext
def close_db(exc):
    d = g.pop("db", None)
    if d is not None:
        d.close()


def load_cards():
    # cards.json is server-owned and not in git; a fresh deploy may not have it yet
    if not os.path.exists(CARDS):
        return []
    with open(CARDS) as f:
        return json.load(f)


def write_cards(cards):
    """Atomically overwrite cards.json (write to a temp file then rename)."""
    fd, tmp = tempfile.mkstemp(dir=SITE)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(cards, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.chmod(tmp, 0o644)
        os.replace(tmp, CARDS)
    except BaseException:
        os.unlink(tmp)
        raise


@app.get("/")
def index():
    return send_from_directory(SITE, "index.html")


# Fetched by browsers when installing the site as an app (PWA)
@app.get("/manifest.json")
@app.get("/icon-192.png")
@app.get("/icon-512.png")
def pwa_asset():
    return send_from_directory(SITE, request.path.lstrip("/"))


@app.get("/api/cards")
def get_cards():
    return jsonify(load_cards())


@app.get("/api/study")
def study():
    """Every card, annotated with its Leitner progress and whether it's due."""
    today = date.today().isoformat()
    rows = {r["front"]: r for r in db().execute("SELECT * FROM review")}
    out = []
    for c in load_cards():
        r = rows.get(c["front"])
        out.append({
            "topic": c.get("topic", ""),
            "front": c["front"],
            "back": c["back"],
            "box": r["box"] if r else 0,          # box 0 = never studied ("new")
            "due": True if r is None else r["due"] <= today,
        })
    return jsonify(out)


@app.post("/api/review")
def review():
    """Record one rating. Open (no password) — it's part of normal studying."""
    body = request.get_json(silent=True) or {}
    front = body.get("front")
    result = body.get("result")
    if not isinstance(front, str) or result not in ("got", "missed"):
        return jsonify(error="need front and result of 'got' or 'missed'"), 400

    row = db().execute("SELECT box, seen, correct FROM review WHERE front=?", (front,)).fetchone()
    box = row["box"] if row else 1
    seen = (row["seen"] if row else 0) + 1
    correct = (row["correct"] if row else 0) + (1 if result == "got" else 0)
    box = min(box + 1, MAX_BOX) if result == "got" else 1
    due = (date.today() + timedelta(days=BOX_DAYS[box])).isoformat()

    db().execute(
        "INSERT INTO review (front, box, due, last, seen, correct) "
        "VALUES (?,?,?,?,?,?) ON CONFLICT(front) DO UPDATE SET "
        "box=excluded.box, due=excluded.due, last=excluded.last, "
        "seen=excluded.seen, correct=excluded.correct",
        (front, box, due, date.today().isoformat(), seen, correct),
    )
    db().commit()
    return jsonify(ok=True, box=box, due=due)


@app.post("/api/verify")
def verify():
    """Check the edit password for the web unlock form. No side effects."""
    if not PASSWORD or request.headers.get("X-Edit-Password") != PASSWORD:
        return jsonify(ok=False), 401
    return jsonify(ok=True)


@app.post("/api/cards")
def save_cards():
    if not PASSWORD or request.headers.get("X-Edit-Password") != PASSWORD:
        return jsonify(error="wrong password"), 401
    cards = request.get_json(silent=True)
    # back is optional: add a front on the web now, fill the back in later
    if not isinstance(cards, list) or not all(
        isinstance(c, dict)
        and isinstance(c.get("front"), str) and c["front"].strip()
        and isinstance(c.get("back", ""), str)
        for c in cards
    ):
        return jsonify(error="each card needs a non-empty front"), 400
    cleaned = [
        {
            "topic": str(c.get("topic") or "").strip(),
            "front": c["front"].strip(),
            "back": str(c.get("back") or "").strip(),
        }
        for c in cards
    ]
    write_cards(cleaned)
    return jsonify(ok=True, count=len(cleaned))


FILL_PROMPT = (
    "You are writing the answer side of study flashcards. Each card below has a "
    "number, an optional topic, and a front (the question or term). Write the back: "
    "a clear, accurate, self-contained answer. Keep it concise — 1 to 3 sentences, "
    "no preamble, and do not restate the question. Return ONLY JSON shaped as "
    '{"answers": [{"i": <card number>, "back": <string>}, ...]} with one entry per '
    "card, reusing the given numbers.\n\nCards:\n"
)


def generate_backs(items):
    """items: list of (index, topic, front). Returns {index: back}."""
    lines = []
    for i, topic, front in items:
        tag = f" [topic: {topic}]" if topic else ""
        lines.append(f"{i}.{tag} {front}")
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": FILL_PROMPT + "\n".join(lines)}],
        "temperature": 0.2,
        "max_tokens": 2000,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://learn.fedecuci.com",
            "X-Title": "Learn cue cards",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        body = json.loads(r.read().decode())
    content = body["choices"][0]["message"]["content"].strip()
    fence = re.match(r"(?s)^```(?:json)?\s*(.*?)\s*```$", content)
    if fence:
        content = fence.group(1)
    data = json.loads(content)
    out = {}
    for a in data.get("answers", []):
        try:
            idx, back = int(a["i"]), str(a["back"]).strip()
        except (KeyError, ValueError, TypeError):
            continue
        if back:
            out[idx] = back
    return out


@app.post("/api/fill")
def fill():
    """Ask the model to write the back of every card that's still missing one."""
    if not PASSWORD or request.headers.get("X-Edit-Password") != PASSWORD:
        return jsonify(error="wrong password"), 401
    if not OPENROUTER_KEY:
        return jsonify(error="AI is not configured on the server"), 503
    cards = load_cards()
    todo = [(i, str(c.get("topic") or "").strip(), c["front"])
            for i, c in enumerate(cards) if not str(c.get("back") or "").strip()]
    if not todo:
        return jsonify(ok=True, filled=0, remaining=0)
    todo = todo[:FILL_MAX]
    try:
        answers = generate_backs(todo)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError,
            ValueError, KeyError, IndexError) as e:
        return jsonify(error=f"AI request failed: {e}"), 502
    filled = 0
    for i, _, _ in todo:
        if i in answers:
            cards[i]["back"] = answers[i]
            filled += 1
    if filled:
        cleaned = [
            {
                "topic": str(c.get("topic") or "").strip(),
                "front": str(c.get("front") or "").strip(),
                "back": str(c.get("back") or "").strip(),
            }
            for c in cards
        ]
        write_cards(cleaned)
    remaining = sum(1 for c in cards if not str(c.get("back") or "").strip())
    return jsonify(ok=True, filled=filled, remaining=remaining)
