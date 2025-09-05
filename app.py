# app.py
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import json, os, time
import gacha_fetcher

# serve templates folder at root
app = Flask(__name__, static_folder="templates", static_url_path="")
# VERY permissive CORS for local dev (you can tighten later)
CORS(app, resources={r"/api/*": {"origins": "*"}})

DATA_FILE = "gacha_history_all.json"

# ------------------------------
# Helper: load saved JSON safely
# ------------------------------
def load_history():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

# ------------------------------
# Root: show a simple test UI if available
# ------------------------------
@app.get("/")
def index():
    # if you placed templates/test.html, serve it; otherwise return helpful message
    if os.path.exists(os.path.join("templates", "test.html")):
        return send_from_directory("templates", "test.html")
    return (
        "No test UI found. Use /api/history, /api/stats, or POST /api/fetch (JSON body {\"url\": \"<authlink>\"}).",
        200,
    )

# ------------------------------
# POST /api/fetch — trigger a fetch
# ------------------------------
@app.post("/api/fetch")
def api_fetch():
    body = request.get_json(force=True) or {}
    raw_url = (body.get("url") or body.get("authkey_url") or body.get("authlink") or "").strip()
    region = (body.get("region") or "global").strip().lower()

    if not raw_url:
        return jsonify({"error": "Missing 'url' in JSON body (paste full authkey URL)"}), 400

    base = gacha_fetcher.normalize_url(raw_url, region)
    # quick test
    if not gacha_fetcher.test_link(base):
        return jsonify({"error": "Invalid or expired authkey (test_link failed)"}), 400

    # fetch; fetch_all_gachas should save combined JSON internally
    result = gacha_fetcher.fetch_all_gachas(base)

    # robustly compute counts depending on return shape
    counts = {}
    total = 0
    if isinstance(result, dict):
        if "by_banner" in result and isinstance(result["by_banner"], dict):
            counts = {k: len(v) for k, v in result["by_banner"].items()}
        else:
            # assume result is mapping label->list
            counts = {k: len(v) for k, v in result.items()}
        total = sum(counts.values())
    else:
        # fallback
        rows = load_history()
        total = len(rows)

    return jsonify({"status": "ok", "counts_by_banner": counts, "total": total})

# ------------------------------
# GET /api/history — with optional filters
# ------------------------------
@app.get("/api/history")
def api_history():
    rows = load_history()
    # optional filters
    banner = request.args.get("banner")           # exact banner code or label
    rarity = request.args.get("rarity", type=int) # 3/4/5
    limit  = request.args.get("limit", type=int)  # e.g., 50

    if banner:
        rows = [r for r in rows if (r.get("banner") == banner or r.get("banner_label") == banner)]
    if rarity:
        rows = [r for r in rows if int(r.get("rarity") or r.get("rank_type") or 0) == rarity]
    if limit:
        rows = rows[:max(0, limit)]
    return jsonify(rows)

# ------------------------------
# GET /api/stats — compute counts + pity
# ------------------------------
@app.get("/api/stats")
def api_stats():
    rows = load_history()
    if not rows:
        return jsonify({"error": "No history found. Run /api/fetch first."}), 404

    # normalize rarity to int
    for r in rows:
        if "rarity" not in r:
            try:
                r["rarity"] = int(r.get("rank_type", 0))
            except Exception:
                r["rarity"] = 0

    total = len(rows)
    five = sum(1 for r in rows if int(r.get("rarity") or 0) == 5)
    four = sum(1 for r in rows if int(r.get("rarity") or 0) == 4)

    # compute pity per banner label (pulls since last 5★). Assume rows are NEWEST->OLDEST
    # If your rows are oldest->newest then we reverse them first
    try:
        # detect order by checking timestamps if present
        ordered_newest_first = True
        if rows and rows[-1].get("_ts") and rows[0].get("_ts"):
            ordered_newest_first = rows[0]["_ts"] >= rows[-1]["_ts"]
        if not ordered_newest_first:
            rows_sorted = list(reversed(rows))
        else:
            rows_sorted = rows
    except Exception:
        rows_sorted = rows

    pity = {}
    # gather unique banner labels from rows
    labels = sorted({r.get("banner_label") or r.get("gacha_type_name") or r.get("banner") for r in rows_sorted})
    for label in labels:
        count = 0
        for r in rows_sorted:
            lbl = r.get("banner_label") or r.get("gacha_type_name") or r.get("banner")
            if lbl != label:
                continue
            if int(r.get("rarity") or 0) == 5:
                break
            count += 1
        pity[label] = count

    return jsonify({
        "total_pulls": total,
        "five_star_count": five,
        "four_star_count": four,
        "five_star_rate": round((five / total * 100), 2) if total else 0.0,
        "four_star_rate": round((four / total * 100), 2) if total else 0.0,
        "pity": pity
    })

from flask import send_from_directory

@app.get("/")
def index_page():
    return send_from_directory("templates", "test.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
