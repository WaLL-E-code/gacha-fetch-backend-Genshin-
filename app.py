# app.py
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import gacha_fetcher

app = Flask(__name__, static_folder="templates", static_url_path="")
CORS(app, resources={r"/api/*": {"origins": "*"}})

@app.get("/")
def index_page():
    # serve templates/test.html if present
    return send_from_directory("templates", "test.html")

@app.post("/api/fetch")
def api_fetch():
    body = request.get_json(force=True) or {}
    raw_url = (body.get("url") or body.get("authkey_url") or body.get("authlink") or "").strip()
    region = (body.get("region") or "global").strip().lower()

    if not raw_url:
        return jsonify({"error": "Missing 'url' in JSON body (paste full authkey URL)"}), 400

    base = gacha_fetcher.normalize_url(raw_url, region)
    if not gacha_fetcher.test_link(base):
        return jsonify({"error": "Invalid or expired authkey (test_link failed)"}), 400

    data = gacha_fetcher.fetch_all_gachas(base)
    # return combined rows for local storage + a tiny summary
    combined = data["combined"]
    counts = {label: len(rows) for label, rows in data["by_banner"].items()}
    return jsonify({
        "result": combined,
        "counts_by_banner": counts,
        "total": sum(counts.values())
    })

# old endpoints intentionally disabled to prevent accidental global saves
@app.get("/api/history")
def api_history_disabled():
    return jsonify({"error": "Server history disabled. Use browser-local storage."}), 410

@app.get("/api/stats")
def api_stats_disabled():
    return jsonify({"error": "Server stats disabled. Compute stats in the browser."}), 410

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
