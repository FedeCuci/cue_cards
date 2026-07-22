import json
import os
import sqlite3
import tempfile
from datetime import date, timedelta

from flask import Flask, g, jsonify, request, send_from_directory

BASE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(BASE, "site")
DATA = os.path.join(BASE, "data")
CARDS = os.path.join(SITE, "cards.json")
DB = os.path.join(DATA, "progress.db")
PASSWORD = os.environ.get("EDIT_PASSWORD", "")

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
    with open(CARDS) as f:
        return json.load(f)


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
    # Write to a temp file then rename, so cards.json is never left half-written
    fd, tmp = tempfile.mkstemp(dir=SITE)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.chmod(tmp, 0o644)
        os.replace(tmp, CARDS)
    except BaseException:
        os.unlink(tmp)
        raise
    return jsonify(ok=True, count=len(cleaned))
