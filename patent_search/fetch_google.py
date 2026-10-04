"""文献番号の表(Excel)から Google Patents(日本語ページ)のHTMLを取得し、本文を抽出して Excel に出力する。

python -m patent_search.fetch_google IN.xlsx OUT.xlsx [--html-dir results/html] [--limit N] [--delay 3]

- 取得した生の HTML は --html-dir に保存する（再実行時は取得済みをスキップ）。
- 本文は <section itemprop=...> / <div class="claim"> 等の構造から抽出する。
  Google 側の画面構造は予告なく変わるため、抽出に失敗した行は「抽出状況」に記録する。
- 注意: Google Patents の自動取得は利用規約上の制限を受け得る。件数を絞り、間隔を空けること。
"""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

URL = "https://patents.google.com/patent/{id}/ja"
UA = "Mozilla/5.0 (patent_search research; contact: owner of this repository)"
EXCEL_CELL_MAX = 32000


def _text(node) -> str:
    """ブロック内のインライン要素(<u>, <sub> 等)は改行せず連結し、<br> だけを改行にする。"""
    if node is None:
        return ""
    node = BeautifulSoup(str(node), "lxml")
    for br in node.find_all("br"):
        br.replace_with("\n")
    text = node.get_text("")
    lines = (re.sub(r"[ \t\u3000]+", " ", l).strip() for l in text.splitlines())
    return "\n".join(l for l in lines if l)


def _content(section):
    """見出し(<h2>)を除いた本体。"""
    return section.find(attrs={"itemprop": "content"}) or section if section else None


def extract(html: str) -> dict:
    s = BeautifulSoup(html, "lxml")
    title = s.find(attrs={"itemprop": "title"}) or s.find("h1")
    abstract = s.find("section", attrs={"itemprop": "abstract"})
    desc = s.find("section", attrs={"itemprop": "description"})
    claims_sec = s.find("section", attrs={"itemprop": "claims"})
    # 請求項は <li class="claim"> の中の <div class="claim" num="N"> が実体（li と div の二重取りを避ける）
    claims = []
    if claims_sec:
        for c in claims_sec.find_all("div", class_="claim"):
            claims.append(f"【請求項{c.get('num', len(claims) + 1)}】" + _text(c))
    paras = []
    if desc:
        for p in desc.find_all(class_="description-paragraph"):
            paras.append(f"[{p.get('num', '')}] " + _text(p) if p.get("num") else _text(p))
    out = {
        "title": re.sub(r"\s+", " ", _text(title)).replace(" - Google Patents", ""),
        "abstract": _text(_content(abstract)),
        "claims": "\n".join(claims),
        "description": "\n".join(paras) or _text(_content(desc)),
        "claim_count": len(claims),
    }
    missing = [k for k in ("title", "abstract", "claims", "description") if not out[k]]
    out["extract_status"] = "OK" if not missing else "欠落: " + ",".join(missing)
    return out


def fetch(session: requests.Session, pid: str, html_dir: Path, delay: float):
    """(html, 使った ID, HTTP 状態) を返す。ID は 末尾の種別コードを外した候補も試す。"""
    for cand in dict.fromkeys([pid, re.sub(r"[A-Z]\d?$", "", pid)]):
        path = html_dir / f"{cand}.html"
        if path.exists():
            return path.read_text(encoding="utf-8"), cand, "cache"
        time.sleep(delay)
        r = session.get(URL.format(id=cand), timeout=60, headers={"Accept-Language": "ja"})
        if r.status_code == 200:
            r.encoding = "utf-8"
            path.write_text(r.text, encoding="utf-8")
            return r.text, cand, "200"
        status = str(r.status_code)
    return "", pid, status


def run(df: pd.DataFrame, html_dir: Path, delay: float = 3.0) -> pd.DataFrame:
    """文献番号の表(Google Patents ID(推定) 列を持つ)から取得・抽出し、結果の表を返す。"""
    html_dir = Path(html_dir)
    html_dir.mkdir(parents=True, exist_ok=True)
    sess = requests.Session()
    sess.headers["User-Agent"] = UA
    rows = []
    for _, r in df.iterrows():
        pid = r.get("Google Patents ID(推定)")
        rec = {"文献番号": r["文献番号"], "ID": pid}
        if not isinstance(pid, str) or not pid:
            rec.update({"取得状況": "IDなし"})
        else:
            try:
                html, used, status = fetch(sess, pid, html_dir, delay)
            except requests.RequestException as e:
                html, used, status = "", pid, f"error: {type(e).__name__}"
            rec.update({"使用ID": used, "取得状況": status})
            if html:
                x = extract(html)
                rec.update({"名称(Google)": x["title"], "要約": x["abstract"],
                            "請求項数": x["claim_count"], "請求項": x["claims"],
                            "明細書": x["description"], "抽出状況": x["extract_status"]})
                if len(x["description"]) > EXCEL_CELL_MAX:  # Excel のセル上限対策。全文は HTML 側にある
                    rec["明細書"] = x["description"][:EXCEL_CELL_MAX]
                    rec["抽出状況"] += " / 明細書を切り詰め"
                if len(x["claims"]) > EXCEL_CELL_MAX:
                    rec["請求項"] = x["claims"][:EXCEL_CELL_MAX]
                    rec["抽出状況"] += " / 請求項を切り詰め"
        rows.append(rec)
        print(rec["文献番号"], rec.get("取得状況"), rec.get("抽出状況", ""), flush=True)
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--html-dir", default="results/html")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--delay", type=float, default=3.0)
    a = ap.parse_args()
    df = pd.read_excel(a.input)
    if a.limit:
        df = df.head(a.limit)
    run(df, Path(a.html_dir), a.delay).to_excel(a.output, index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
