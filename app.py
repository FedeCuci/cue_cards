import json
import os
import tempfile

from flask import Flask, jsonify, request, send_from_directory

BASE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(BASE, "site")
CARDS = os.path.join(SITE, "cards.json")
PASSWORD = os.environ.get("EDIT_PASSWORD", "")

app = Flask(__name__)


@app.get("/")
def index():
    return send_from_directory(SITE, "index.html")


@app.get("/api/cards")
def get_cards():
    with open(CARDS) as f:
        return jsonify(json.load(f))


@app.post("/api/cards")
def save_cards():
    if not PASSWORD or request.headers.get("X-Edit-Password") != PASSWORD:
        return jsonify(error="wrong password"), 401
    cards = request.get_json(silent=True)
    if not isinstance(cards, list) or not all(
        isinstance(c, dict)
        and isinstance(c.get("front"), str) and c["front"].strip()
        and isinstance(c.get("back"), str) and c["back"].strip()
        for c in cards
    ):
        return jsonify(error="each card needs a non-empty front and back"), 400
    cleaned = [
        {
            "topic": str(c.get("topic") or "").strip(),
            "front": c["front"].strip(),
            "back": c["back"].strip(),
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
