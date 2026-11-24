import os
from datetime import date, datetime, timedelta

import requests
import urllib3
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()
urllib3.disable_warnings()

AUTHKEY = os.getenv("AUTHKEY")
URL = "https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON"

app = Flask(__name__)
_cache = {}  # {"YYYYMMDD": [환율 데이터...]}


def to_float(s):
    return float(str(s).replace(",", ""))


def fetch_rates(d):
    """d: 'YYYYMMDD'. 환율 리스트 반환 (데이터 없으면 [])."""
    if d in _cache:
        return _cache[d]
    try:
        res = requests.get(
            URL,
            params={"authkey": AUTHKEY, "searchdate": d, "data": "AP01"},
            timeout=10,
            verify=False,
        )
        data = res.json()
    except Exception:
        return []

    rates = [r for r in data if r.get("result") == 1]
    today_str = date.today().strftime("%Y%m%d")
    if rates or (data == [] and d < today_str):
        _cache[d] = rates
    return rates


def find_prev(d):
    """d 이전의 가장 가까운 영업일 환율 (전일 대비 계산용)."""
    day = datetime.strptime(d, "%Y%m%d").date()
    for i in range(1, 8):
        cand = day - timedelta(days=i)
        if cand.weekday() >= 5:
            continue
        rates = fetch_rates(cand.strftime("%Y%m%d"))
        if rates:
            return rates
    return []


@app.route("/")
def index():
    picked = request.args.get("date")  # 'YYYY-MM-DD'
    d, rates = None, []

    if picked:
        d = picked.replace("-", "")
        rates = fetch_rates(d)
    else:
        for i in range(7):
            cand = (date.today() - timedelta(days=i)).strftime("%Y%m%d")
            rates = fetch_rates(cand)
            if rates:
                d = cand
                break

    msg = None
    if not rates:
        msg = "데이터가 없어요. 주말·공휴일·오전 11시 이전이거나 인증키 문제일 수 있어요."

    rows = []
    if rates:
        prev = {r["cur_unit"]: to_float(r["deal_bas_r"]) for r in find_prev(d)}
        for r in rates:
            if r["cur_unit"] == "KRW":
                continue
            rate = to_float(r["deal_bas_r"])
            p = prev.get(r["cur_unit"])
            diff = round(rate - p, 2) if p else None
            pct = round((rate - p) / p * 100, 2) if p else None
            rows.append(
                {"unit": r["cur_unit"], "name": r["cur_nm"], "rate": rate, "diff": diff, "pct": pct}
            )

    payload = {
        "rows": rows,
        "msg": msg,
        "date": f"{d[:4]}-{d[4:6]}-{d[6:]}" if d else "",
        "today": date.today().isoformat(),
    }
    return render_template("index.html", payload=payload)


@app.route("/api/history")
def history():
    cur = request.args.get("cur", "USD")
    days = min(request.args.get("days", 14, type=int), 30)

    points = []
    for i in range(days, -1, -1):
        day = date.today() - timedelta(days=i)
        if day.weekday() >= 5:
            continue
        for r in fetch_rates(day.strftime("%Y%m%d")):
            if r["cur_unit"] == cur:
                points.append({"date": day.isoformat(), "rate": to_float(r["deal_bas_r"])})
    return jsonify(points)


if __name__ == "__main__":
    app.run(debug=True)