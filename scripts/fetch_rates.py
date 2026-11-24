import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()

AUTHKEY = os.getenv("AUTHKEY")
URL = "https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON"
OUT = Path(__file__).resolve().parent.parent / "data" / "rates.json"
KST = timezone(timedelta(hours=9))


class FatalApiError(Exception):
    """인증키 오류, 일일 호출 제한 등 더 시도해도 의미 없는 오류"""


def to_float(s):
    return float(str(s).replace(",", ""))


def fetch(d):
    """d: date. 환율 리스트 반환 (데이터 없으면 [])."""
    params = {"authkey": AUTHKEY, "searchdate": d.strftime("%Y%m%d"), "data": "AP01"}
    try:
        res = requests.get(URL, params=params, timeout=20)
    except requests.exceptions.SSLError:
        res = requests.get(URL, params=params, timeout=20, verify=False)
    data = res.json()

    for item in data:
        code = item.get("result")
        if code in (3, 4):
            raise FatalApiError(f"API 오류 result={code} (3=인증키 오류, 4=일일 호출 제한)")
        if code not in (1, None):
            raise RuntimeError(f"API 오류 result={code}")

    return [
        {"unit": r["cur_unit"], "name": r["cur_nm"], "rate": to_float(r["deal_bas_r"])}
        for r in data
        if r.get("cur_unit") and r["cur_unit"] != "KRW"
    ]


def main():
    if not AUTHKEY:
        sys.exit("AUTHKEY 환경변수가 없어요.")

    store = {"updated": "", "days": {}}
    if OUT.exists():
        store = json.loads(OUT.read_text(encoding="utf-8"))
    have = store["days"]

    n = int(os.getenv("DAYS") or (7 if have else 30))
    if not have:
        n = max(n, 30)  # 처음엔 최소 30일 치를 채워요

    today = datetime.now(KST).date()
    added = ok = errors = 0
    fatal = None

    for i in range(n, -1, -1):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:  # 주말 제외
            continue
        key = d.isoformat()
        if have.get(key):  # 이미 받은 날짜는 건너뜀
            continue
        try:
            rows = fetch(d)
        except FatalApiError as e:
            fatal = str(e)
            print(f"{key}: {fatal}")
            break
        except Exception as e:
            errors += 1
            print(f"{key}: 실패 - {e}")
            continue

        ok += 1
        if rows:
            have[key] = rows
            added += 1
            print(f"{key}: {len(rows)}개 통화 저장")
        else:
            print(f"{key}: 데이터 없음 (휴일이거나 아직 미공개)")

    if added:
        store["days"] = dict(sorted(have.items()))
        store["updated"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M (KST)")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(store, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"저장 완료: {added}일 추가")
    else:
        print("새로 추가된 데이터가 없어요.")

    if fatal or (errors and not ok):
        sys.exit(1)  # Actions에서 실패로 표시되도록


if __name__ == "__main__":
    main()