"""
權證雷達 - 核心邏輯
從桌面版 搜尋.py 移植，去除所有 Tkinter/GUI 相依，供 Flask 後端使用。
"""
import math
import statistics
import urllib.parse
import json

import requests

# ──────────────────────────────────────────────────────────────────
#  權證 API
# ──────────────────────────────────────────────────────────────────
API_URL = "https://www.warrantwin.com.tw/eyuanta/ws/GetWarData.ashx"
API_COLS = [
    "FLD_WAR_ID", "FLD_WAR_NM", "FLD_WAR_TYPE", "FLD_ISSUE_AGT_ID",
    "FLD_UND_ID", "FLD_UND_NM",
    "FLD_OBJ_TXN_PRICE", "FLD_OBJ_UP_DN_RATE", "FLD_OBJ_TTL_VOLUME",
    "FLD_WAR_UP_DN_RATE", "FLD_WAR_TXN_PRICE",
    "FLD_WAR_TXN_VOLUME", "FLD_WAR_TTL_VOLUME",
    "FLD_WAR_BUY_PRICE", "FLD_WAR_SELL_PRICE",
    "FLD_DUR_END", "FLD_OUT_TOT_BAL_VOL", "FLD_OUT_VOL_RATE",
    "FLD_N_STRIKE_PRC", "FLD_N_UND_CONVER", "FLD_PERIOD",
    "FLD_IV_BUY_PRICE", "FLD_IV_SELL_PRICE",
    "FLD_DELTA", "FLD_THETA", "FLD_IN_OUT", "FLD_LEVERAGE",
    "FLD_PFR_PCT",
]
HDRS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://www.warrantwin.com.tw",
    "Referer": "https://www.warrantwin.com.tw/eyuanta/Warrant/Search.aspx",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


class WarrantAPI:
    def __init__(self):
        self.sess = requests.Session()
        self.sess.headers.update(HDRS)

    def fetch_all(self, stock_no, war_types):
        rows, page = [], 1
        while True:
            batch, pages = self._page(stock_no, war_types, page)
            rows.extend(batch)
            if page >= pages:
                break
            page += 1
        return rows

    def _page(self, stock_no, war_types, page=1, row=100):
        body = {
            "format": "JSON",
            "factor": {
                "columns": API_COLS,
                "condition": [
                    {"field": "FLD_UND_ID", "values": [str(stock_no)]},
                    {"field": "FLD_WAR_TYPE", "values": war_types},
                ],
                "orderby": {"field": "FLD_WAR_ID", "sort": "ASC"},
            },
            "pagination": {"row": row, "page": str(page)},
            "callback": 1,
        }
        try:
            r = self.sess.post(
                API_URL,
                data="data=" + urllib.parse.quote(json.dumps(body, ensure_ascii=False)),
                timeout=20,
            )
            raw = r.json()
            return raw.get("result", []), int(raw.get("pages", 1))
        except Exception as e:
            print(f"[API] {e}")
            return [], 1


# ──────────────────────────────────────────────────────────────────
#  股票期貨保證金（期交所開放 API）
# ──────────────────────────────────────────────────────────────────
MARGIN_STOCK_URL = "https://openapi.taifex.com.tw/v1/SingleStockFuturesMargining"
MARGIN_ETF_URL = "https://openapi.taifex.com.tw/v1/SingleStockFuturesETFMargining"


class MarginAPI:
    def __init__(self):
        self.stock_rows = None
        self.etf_rows = None

    def _ensure_loaded(self):
        if self.stock_rows is not None:
            return
        self.stock_rows, self.etf_rows = {}, {}
        try:
            resp = requests.get(MARGIN_STOCK_URL, timeout=10)
            try:
                # 期交所 open API 正常應回傳 JSON
                for row in resp.json():
                    self.stock_rows.setdefault(row.get("UnderlyingSecurityCode", ""), []).append(row)
            except ValueError:
                # 目前實際觀測到此端點回傳 CSV（非 JSON），改用 CSV 解析
                import csv
                import io
                resp.encoding = "utf-8-sig"
                for row in csv.DictReader(io.StringIO(resp.text)):
                    code = (row.get("股票期貨標的證券代號") or "").strip()
                    self.stock_rows.setdefault(code, []).append({
                        "ContractName": (row.get("股票期貨中文簡稱") or "").strip(),
                        "InitialMarginRate": (row.get("原始保證金適用比例") or "").strip(),
                    })
        except Exception as e:
            print(f"[margin stock] {e}")
        try:
            for row in requests.get(MARGIN_ETF_URL, timeout=10).json():
                self.etf_rows.setdefault(row.get("UnderlyingSecurityCode", ""), []).append(row)
        except Exception as e:
            print(f"[margin etf] {e}")

    def get_margin(self, code, price=0.0):
        """回傳 [(label, 金額), ...]，label 為 '原始' 或 '小'；查無資料回傳 []"""
        self._ensure_loaded()

        def is_mini(row):
            return row.get("ContractName", "").startswith("小")

        rows = self.etf_rows.get(code)
        if rows:
            out = []
            for row in sorted(rows, key=is_mini):
                try:
                    amt = int(row.get("InitialMargin", 0))
                except Exception:
                    continue
                out.append(("小" if is_mini(row) else "原始", amt))
            return out

        rows = self.stock_rows.get(code)
        if rows and price and price > 0:
            out = []
            for row in sorted(rows, key=is_mini):
                try:
                    rate = float(str(row.get("InitialMarginRate", "0")).replace("%", "")) / 100
                except Exception:
                    continue
                mult = 100 if is_mini(row) else 2000
                out.append(("小" if is_mini(row) else "原始", math.ceil(price * mult * rate)))
            return out
        return []


def check_stock_futures(code, price, margin_api: MarginAPI):
    """查詢台灣期交所是否有該股票的股票期貨，並回傳原始保證金（含小型契約）"""
    try:
        r = requests.get(
            "https://www.taifex.com.tw/cht/2/stockLists",
            params={"commodity_id": "SF"},
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        has_sf = code in r.text
        margins = margin_api.get_margin(code, price) if has_sf else []
        return has_sf, margins
    except Exception as e:
        print(f"[futures] {e}")
        return False, []


# ──────────────────────────────────────────────────────────────────
#  正規化
# ──────────────────────────────────────────────────────────────────
def _bs_fair(S, K, T, sigma, r, ratio, is_call):
    """Black-Scholes 權證合理價（用買價IV）"""
    if T <= 0 or sigma <= 0 or K <= 0 or S <= 0 or ratio <= 0:
        return 0.0
    sqT = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqT)
    d2 = d1 - sigma * sqT
    N = lambda x: 0.5 * math.erfc(-x / math.sqrt(2))
    if is_call:
        price = S * N(d1) - K * math.exp(-r * T) * N(d2)
    else:
        price = K * math.exp(-r * T) * N(-d2) - S * N(-d1)
    return price * ratio


def normalize(r):
    def flt(*ks, d=0.0):
        for k in ks:
            v = r.get(k)
            if v not in (None, "", "-"):
                try:
                    return float(str(v).replace("%", "").replace(",", ""))
                except Exception:
                    pass
        return d

    def s(*ks, d=""):
        for k in ks:
            v = r.get(k)
            if v not in (None, ""):
                return str(v)
        return d

    bid = flt("FLD_WAR_BUY_PRICE")
    ask = flt("FLD_WAR_SELL_PRICE")
    wp = flt("FLD_WAR_TXN_PRICE") or bid

    spread_pct = (ask - bid) / ask * 100 if ask > 0 else 99.0
    iv_buy = flt("FLD_IV_BUY_PRICE")
    iv_sell = flt("FLD_IV_SELL_PRICE")
    lev = flt("FLD_LEVERAGE")
    sl_ratio = spread_pct / lev if lev > 0 else 99.0

    und = flt("FLD_OBJ_TXN_PRICE")
    stk = flt("FLD_N_STRIKE_PRC")
    mn = (und - stk) / stk * 100 if stk > 0 else 0.0

    ratio = flt("FLD_N_UND_CONVER")
    days = flt("FLD_PERIOD")
    is_call = s("FLD_WAR_TYPE") in ("1", "認購")
    fair = _bs_fair(und, stk, days / 365, iv_buy / 100, 0.015, ratio, is_call)
    fair_diff = (ask - fair) / fair * 100 if fair > 0 else 0.0

    return {
        "code": s("FLD_WAR_ID"),
        "name": s("FLD_WAR_NM"),
        "war_type": s("FLD_WAR_TYPE"),
        "und_id": s("FLD_UND_ID"),
        "und_nm": s("FLD_UND_NM"),
        "und_price": und,
        "und_chg": flt("FLD_OBJ_UP_DN_RATE"),
        "und_vol": flt("FLD_OBJ_TTL_VOLUME"),
        "war_price": wp,
        "war_chg": flt("FLD_WAR_UP_DN_RATE"),
        "qty": flt("FLD_WAR_TXN_VOLUME"),
        "out_qty": flt("FLD_OUT_TOT_BAL_VOL"),
        "bid": bid, "ask": ask,
        "spread_pct": round(spread_pct, 3),
        "sl_ratio": round(sl_ratio, 4),
        "expire": s("FLD_DUR_END"),
        "days": flt("FLD_PERIOD"),
        "iv_buy": iv_buy, "iv_sell": iv_sell,
        "bid_ask_iv": round(abs(iv_buy - iv_sell), 2),
        "delta": flt("FLD_DELTA"),
        "theta": flt("FLD_THETA"),
        "eff_lev": lev,
        "strike": stk,
        "ratio": flt("FLD_N_UND_CONVER"),
        "out_rate": flt("FLD_OUT_VOL_RATE"),
        "premium": flt("FLD_PFR_PCT"),
        "moneyness": round(mn, 2),
        "fair": round(fair, 2),
        "fair_diff": round(fair_diff, 2),
    }


# ──────────────────────────────────────────────────────────────────
#  條件系統
# ──────────────────────────────────────────────────────────────────
FIELD_META = {
    "sl_ratio": ("差槓比", "%"),
    "eff_lev": ("實質槓桿", "倍"),
    "spread_pct": ("價差比", "%"),
    "moneyness": ("價內外%", "%"),
    "days": ("剩餘天數", "天"),
    "out_rate": ("外流通率", "%"),
    "war_price": ("成交價", "元"),
    "delta": ("Delta", ""),
    "premium": ("溢價率", "%"),
    "bid_ask_iv": ("買賣IV差", ""),
    "iv_buy": ("買價隱波", "%"),
    "iv_dev": ("IV偏離", "%"),
    "qty": ("今日成交量", "張"),
    "out_qty": ("流通在外量", "張"),
}

COL_TIPS = {
    "code": "權證代碼（6位數字）\n點擊可開啟元大權證網「權證分析」頁面",
    "name": "權證名稱（含標的、發行商、履約月份）",
    "sl_ratio": "差槓比 = 價差比 ÷ 實質槓桿\n< 0.3 較優  |  > 1.0 不適合",
    "eff_lev": "實質槓桿倍數\n反映標的漲1%，權證漲幾%\n建議 5~15倍",
    "spread_pct": "價差比 = (委賣價 - 委買價) ÷ 委賣價 × 100%\n超過 5% 代表流動性差",
    "moneyness": "價內外% = (標的價 - 履約價) ÷ 履約價 × 100\n正值=價內  負值=價外\n建議 -5% ~ +10%",
    "days": "剩餘天數（到期日距今）\n建議 > 90 天",
    "out_rate": "外流通率 = 流通在外張數 ÷ 發行總量 × 100%\n< 20% 發行商可能停止報價",
    "war_price": "權證最新成交價（元）\n太低（< 0.5）流動性往往較差",
    "bid": "買進最佳報價",
    "ask": "賣出最佳報價",
    "delta": "Delta：標的漲1元，權證理論漲幾元（× 行使比）",
    "premium": "溢價率% = (實際買入成本 - 標的現值) ÷ 標的現值 × 100",
    "bid_ask_iv": "買賣隱含波動率差（買IV - 賣IV）\n越小代表報價越一致",
    "iv_buy": "買進隱含波動率（IV）",
    "iv_sell": "賣出隱含波動率（IV）",
    "theta": "Theta：每日時間價值損耗（元）",
    "war_chg": "今日權證漲跌幅%",
    "qty": "今日成交量（張）",
    "out_qty": "流通在外張數",
    "strike": "履約價（元）",
    "ratio": "行使比例：幾張權證換1單位標的",
    "expire": "到期日",
    "fair": "合理價（元）\nBlack-Scholes × 買價IV 計算出的理論價",
    "fair_diff": "高估%\n正值=你買進比合理價貴幾%；越小越好",
    "iv_avg": "同類IV：同標的、同類型（認購/認售）買價隱波中位數",
    "iv_dev": "IV偏離% = (買價IV - 同類IV) ÷ 同類IV × 100\n正值=被高估  負值=相對便宜",
    "iv_stable": "IV評價\n▲偏高：IV高於同類10%以上，避開\n▼偏低：IV低於同類10%以上，相對便宜\n⚠IV差大：買賣IV差>3，報價不穩\n✓穩定：IV接近同類且報價一致",
}

DEF_CONDITIONS = [
    {
        "name": "差槓比",
        "color": "#3fb950",
        "rules": [
            {"field": "sl_ratio", "op": "<", "value": 0.3},
            {"field": "eff_lev", "op": ">=", "value": 5.0},
        ],
    },
    {
        "name": "江大",
        "color": "#58a6ff",
        "rules": [
            {"field": "moneyness", "op": "between", "value": [-5.0, 10.0]},
            {"field": "days", "op": ">", "value": 90},
            {"field": "out_rate", "op": "<=", "value": 50.0},
            {"field": "war_price", "op": ">=", "value": 1.5},
        ],
    },
    {"name": "自訂3", "color": "#d29922", "rules": []},
    {"name": "自訂4", "color": "#bc8cff", "rules": []},
    {"name": "自訂5", "color": "#e3a84a", "rules": []},
]

# (id, 標題, 預設顯示)
FREE_COLS_DEF = [
    ("sl_ratio", "差槓比", True),
    ("eff_lev", "槓桿", True),
    ("spread_pct", "價差%", True),
    ("moneyness", "價內外%", True),
    ("days", "剩餘天", True),
    ("out_rate", "外流通%", True),
    ("war_price", "成交價", True),
    ("bid", "買價", True),
    ("ask", "賣價", True),
    ("delta", "Delta", True),
    ("premium", "溢價率", False),
    ("bid_ask_iv", "IV差", False),
    ("iv_buy", "買IV", False),
    ("iv_sell", "賣IV", False),
    ("iv_avg", "同類IV", True),
    ("iv_dev", "IV偏離", True),
    ("iv_stable", "IV評價", True),
    ("theta", "Theta", False),
    ("war_chg", "漲跌幅", True),
    ("qty", "成交量", True),
    ("out_qty", "流通張數", False),
    ("strike", "履約價", True),
    ("ratio", "行使比", False),
    ("expire", "到期日", True),
    ("fair", "合理價", True),
    ("fair_diff", "高估%", True),
]


def eval_cond(row: dict, cond: dict) -> bool:
    for rule in cond.get("rules", []):
        f = rule["field"]
        op = rule["op"]
        v = rule["value"]
        rv = row.get(f, 0.0)
        if op == ">":
            if not (rv > v):
                return False
        elif op == "<":
            if not (rv < v):
                return False
        elif op == ">=":
            if not (rv >= v):
                return False
        elif op == "<=":
            if not (rv <= v):
                return False
        elif op == "between":
            lo, hi = v
            if rv == 0.0 and f == "out_rate":
                pass
            elif not (lo <= rv <= hi):
                return False
    return True


def eval_all_conds(row, conditions):
    row["_conds"] = [eval_cond(row, c) for c in conditions]


def calc_iv_stats(rows):
    """同類IV比較：同類型（認購/認售）買價IV中位數 → 偏離% → 評價"""
    groups = {}
    for r in rows:
        groups.setdefault(r.get("war_type", ""), []).append(r)
    for grp in groups.values():
        ivs = [r["iv_buy"] for r in grp if r.get("iv_buy", 0) > 0]
        med = statistics.median(ivs) if ivs else 0.0
        for r in grp:
            r["iv_avg"] = round(med, 2)
            if med > 0 and r.get("iv_buy", 0) > 0:
                dev = (r["iv_buy"] - med) / med * 100
            else:
                dev = 0.0
            r["iv_dev"] = round(dev, 2)
            if r.get("iv_buy", 0) <= 0 or med <= 0:
                r["iv_stable"] = "-"
            elif dev > 10:
                r["iv_stable"] = "▲偏高"
            elif dev < -10:
                r["iv_stable"] = "▼偏低"
            elif r.get("bid_ask_iv", 0) > 3:
                r["iv_stable"] = "⚠IV差大"
            else:
                r["iv_stable"] = "✓穩定"
