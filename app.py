"""
權證雷達 Web 版
以 Flask 包裝 core.py 的查詢/篩選邏輯，提供手機瀏覽器可用的介面。
"""
import json
import os
import threading
from functools import wraps

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

import core

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
WATCH_FILE = os.path.join(DATA_DIR, "watchlist.json")
COND_FILE = os.path.join(DATA_DIR, "conditions.json")

APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")

app = Flask(__name__)
app.secret_key = SECRET_KEY

api = core.WarrantAPI()
margin_api = core.MarginAPI()
threading.Thread(target=margin_api._ensure_loaded, daemon=True).start()


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_conditions():
    conds = load_json(COND_FILE, None)
    if not conds:
        conds = [dict(c) for c in core.DEF_CONDITIONS]
    while len(conds) < 5:
        conds.append(dict(core.DEF_CONDITIONS[len(conds)]))
    return conds


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if APP_PASSWORD and not session.get("ok"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("login"))
        return fn(*a, **kw)
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    if not APP_PASSWORD:
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        if request.form.get("password") == APP_PASSWORD:
            session["ok"] = True
            return redirect(url_for("index"))
        error = "密碼錯誤"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    return render_template(
        "index.html",
        field_meta=core.FIELD_META,
        col_tips=core.COL_TIPS,
        free_cols=core.FREE_COLS_DEF,
        def_conditions=core.DEF_CONDITIONS,
    )


@app.route("/api/watchlist", methods=["GET"])
@login_required
def api_get_watchlist():
    return jsonify(load_json(WATCH_FILE, []))


@app.route("/api/watchlist", methods=["POST"])
@login_required
def api_add_watchlist():
    code = (request.json or {}).get("code", "").strip()
    if not code:
        return jsonify({"error": "empty code"}), 400
    wl = load_json(WATCH_FILE, [])
    if not any(s["code"] == code for s in wl):
        wl.append({"code": code, "name": code, "price": "-", "chg": 0.0, "vol": "-"})
        save_json(WATCH_FILE, wl)
    return jsonify(wl)


@app.route("/api/watchlist/<code>", methods=["DELETE"])
@login_required
def api_del_watchlist(code):
    wl = load_json(WATCH_FILE, [])
    wl = [s for s in wl if s["code"] != code]
    save_json(WATCH_FILE, wl)
    return jsonify(wl)


@app.route("/api/conditions", methods=["GET"])
@login_required
def api_get_conditions():
    return jsonify(get_conditions())


@app.route("/api/conditions", methods=["POST"])
@login_required
def api_set_conditions():
    conds = request.json or []
    save_json(COND_FILE, conds)
    return jsonify(conds)


@app.route("/api/quote")
@login_required
def api_quote():
    code = request.args.get("code", "").strip()
    wtype = request.args.get("type", "全部")
    if not code:
        return jsonify({"error": "missing code"}), 400

    wt_map = {"認購": ["1"], "認售": ["2"], "全部": ["1", "2"]}
    raw = api.fetch_all(code, wt_map.get(wtype, ["1", "2"]))
    if not raw:
        return jsonify({"stock": None, "rows": [], "conditions": get_conditions()})

    rows = [core.normalize(r) for r in raw]
    rows = [r for r in rows if r["und_id"] == code]

    conds = get_conditions()
    for row in rows:
        core.eval_all_conds(row, conds)
    core.calc_iv_stats(rows)

    stock_info = None
    for r in rows:
        if r["und_price"] > 0:
            stock_info = {
                "code": code,
                "name": r["und_nm"] or code,
                "price": r["und_price"],
                "chg": r["und_chg"],
                "vol": r["und_vol"],
            }
            break

    if stock_info:
        wl = load_json(WATCH_FILE, [])
        changed = False
        for s in wl:
            if s["code"] == code:
                s.update({
                    "name": stock_info["name"],
                    "price": stock_info["price"],
                    "chg": stock_info["chg"],
                    "vol": f"{int(stock_info['vol']):,}" if stock_info["vol"] else "-",
                })
                changed = True
        if changed:
            save_json(WATCH_FILE, wl)

    return jsonify({"stock": stock_info, "rows": rows, "conditions": conds})


@app.route("/api/futures")
@login_required
def api_futures():
    code = request.args.get("code", "").strip()
    try:
        price = float(request.args.get("price", 0) or 0)
    except ValueError:
        price = 0.0
    if not code:
        return jsonify({"error": "missing code"}), 400
    has_sf, margins = core.check_stock_futures(code, price, margin_api)
    return jsonify({"has_sf": has_sf, "margins": margins})


@app.route("/api/debug_probe")
@login_required
def api_debug_probe():
    """暫時性診斷端點：直接打元大權證網 API，回傳原始 HTTP 狀態與內容片段，
    用來判斷伺服器端（例如 Render）是否被目標網站擋下。確認問題後可移除此端點。"""
    import json as _json
    import urllib.parse as _urlparse

    code = request.args.get("code", "2379").strip()
    body = {
        "format": "JSON",
        "factor": {
            "columns": core.API_COLS,
            "condition": [
                {"field": "FLD_UND_ID", "values": [str(code)]},
                {"field": "FLD_WAR_TYPE", "values": ["1", "2"]},
            ],
            "orderby": {"field": "FLD_WAR_ID", "sort": "ASC"},
        },
        "pagination": {"row": 5, "page": "1"},
        "callback": 1,
    }
    try:
        r = api.sess.post(
            core.API_URL,
            data="data=" + _urlparse.quote(_json.dumps(body, ensure_ascii=False)),
            timeout=20,
        )
        return jsonify({
            "status_code": r.status_code,
            "content_type": r.headers.get("Content-Type"),
            "body_preview": r.text[:1500],
        })
    except Exception as e:
        return jsonify({"exception": str(e)})


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
