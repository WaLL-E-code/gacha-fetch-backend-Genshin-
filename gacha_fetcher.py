# gacha_fetcher.py
import json, time, csv
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from datetime import datetime
import requests

REQUEST_DELAY = 0.5
FETCH_PAGE_SIZE = 20
OUTPUT_JSON = "gacha_history_all.json"
OUTPUT_CSV  = "gacha_history_all.csv"

# Banner codes & labels used by Hoyoverse
GACHA_TYPES = {
    "100": "Beginner",
    "200": "Standard",
    "301": "Character Event",
    "302": "Weapon Event",
    "500": "Chronicled",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://webstatic.mihoyo.com/",
}

def normalize_url(raw_url: str, region: str = "global") -> str:
    """Coerce to the official endpoint, strip paging params, keep authkey."""
    p = urlparse(raw_url)
    host = "public-operation-hk4e-sg.hoyoverse.com" if region == "global" else "public-operation-hk4e.mihoyo.com"
    path = "/gacha_info/api/getGachaLog"
    q = parse_qs(p.query)
    for k in ["page", "size", "end_id"]:
        q.pop(k, None)
    # language + game_biz safety
    q.setdefault("lang", ["en"])
    if not q.get("game_biz") or not q["game_biz"][0]:
        q["game_biz"] = ["hk4e_global" if region == "global" else "hk4e_cn"]
    return urlunparse((p.scheme or "https", host, path, "", urlencode(q, doseq=True), ""))

def _request_json(url: str) -> dict:
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()

def test_link(api_base_url: str) -> bool:
    try:
        js = _request_json(f"{api_base_url}&gacha_type=301&size=5")
        return int(js.get("retcode", -1)) == 0
    except Exception:
        return False

def fetch_banner(api_base_url: str, gacha_type: str) -> list:
    rows, page, end_id = [], 1, None
    while True:
        url = f"{api_base_url}&gacha_type={gacha_type}&page={page}&size={FETCH_PAGE_SIZE}"
        if end_id:
            url += f"&end_id={end_id}"
        try:
            js = _request_json(url)
        except Exception:
            break
        data_rows = (js.get("data") or {}).get("list") or []
        if not data_rows:
            break

        # transform rows to a consistent schema
        for r in data_rows:
            # API fields: id, name, item_type, rank_type, time, gacha_type, etc.
            r["banner"]        = gacha_type                               # "301"
            r["banner_label"]  = GACHA_TYPES.get(gacha_type, gacha_type)  # "Character Event"
            r["rarity"]        = int(r.get("rank_type", 0))               # 3/4/5 as int
            # keep 'time' as-is; also compute sortable ts (best-effort)
            try:
                r["_ts"] = int(datetime.strptime(r["time"], "%Y-%m-%d %H:%M:%S").timestamp())
            except Exception:
                r["_ts"] = 0

        rows.extend(data_rows)
        end_id = data_rows[-1]["id"]
        page += 1
        time.sleep(REQUEST_DELAY)
    return rows

def dedupe_and_sort(all_rows: list) -> list:
    # dedupe by unique 'id' (API gives a monotonic id string)
    seen, out = set(), []
    for r in all_rows:
        rid = r.get("id")
        if rid and rid not in seen:
            seen.add(rid)
            out.append(r)
    # newest first (descending time)
    out.sort(key=lambda r: (r.get("_ts", 0), r.get("id", "")), reverse=True)
    return out

def save_history(rows: list):
    # JSON
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    # CSV (optional but handy)
    field_order = ["id", "name", "item_type", "rarity", "banner", "banner_label", "time", "uid"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=field_order)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in field_order})

def fetch_all_gachas(api_base_url: str) -> dict:
    all_rows, by_banner = [], {}
    for gtype, label in GACHA_TYPES.items():
        rows = fetch_banner(api_base_url, gtype)
        if rows:
            by_banner[label] = rows
            all_rows.extend(rows)
    combined = dedupe_and_sort(all_rows)
    save_history(combined)
    return {"by_banner": by_banner, "combined": combined}

def calc_stats(rows: list) -> dict:
    total = len(rows)
    c5   = sum(1 for r in rows if r.get("rarity") == 5)
    c4   = sum(1 for r in rows if r.get("rarity") == 4)
    # pity per label = pulls since last 5★ looking from newest to oldest
    pity = {label: 0 for label in GACHA_TYPES.values()}
    for label in pity.keys():
        for r in rows:  # rows are newest→oldest already
            if r.get("banner_label") != label:
                continue
            if r.get("rarity") == 5:
                break
            pity[label] += 1
    return {
        "total_pulls": total,
        "five_star_count": c5,
        "four_star_count": c4,
        "five_star_rate": round((c5 / total * 100), 2) if total else 0.0,
        "four_star_rate": round((c4 / total * 100), 2) if total else 0.0,
        "pity": pity,
    }
