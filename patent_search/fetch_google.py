"""プログラム2: 文献番号の表から Google Patents(日本語ページ)の HTML を取得し、本文を抽出して保存する。

作業の流れ:
 1. fetch         : 1 件分の URL にアクセスして HTML を取得し、results/html/ に保存する(取得済みは再利用)
 2. extract       : HTML から、名称・要約・請求項・明細書(段落番号つき)を取り出す
 3. save_fulltext : 全文を切り詰めずに JSON で保存する(原文と、全角を半角に揃えた NFKC 版)
    Web から取れず、入力が CSV で要約がある場合は、その要約だけを本文として保存する(出所を記録)
 4. run           : 上の 1〜3 を表の全行に対して繰り返し、結果の表(Excel 出力用)を返す

python -m patent_search.fetch_google IN.xlsx OUT.xlsx [--html-dir results/html] [--limit N] [--delay 3]

- 取得した生の HTML は --html-dir に保存する（再実行時は取得済みをスキップ）。
- 本文は <section itemprop=...> / <div class="claim"> 等の構造から抽出する。
  Google 側の画面構造は予告なく変わるため、抽出に失敗した行は「抽出状況」に記録する。
- 注意: Google Patents の自動取得は利用規約上の制限を受け得る。件数を絞り、間隔を空けること。
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
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


# 作業: <section> から見出し(<h2>)を除いた本体部分だけを返す。
def _content(section):
    """見出し(<h2>)を除いた本体。"""
    return section.find(attrs={"itemprop": "content"}) or section if section else None


# 作業: Google Patents のページ構造(itemprop 属性)から、名称・要約・請求項・明細書を取り出す。
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
    out["extract_status"] = extract_status(out)
    return out


# 作業: 名称・要約・請求項・明細書のうち、取れなかった項目を判定する(全部あれば OK)。
def extract_status(x: dict) -> str:
    missing = [k for k in ("title", "abstract", "claims", "description") if not x[k]]
    return "OK" if not missing else "欠落: " + ",".join(missing)


# 作業: 1 件の HTML を取得する。調査フォルダにあればそれを使い、
# なければ共有キャッシュ(cache_dir)から複写し、それもなければ通信して両方に保存する。
def fetch(session: requests.Session, pid: str, html_dir: Path, delay: float, cache_dir: Path | None = None):
    """(html, 使った ID, HTTP 状態) を返す。ID は 末尾の種別コードを外した候補も試す。"""
    for cand in dict.fromkeys([pid, re.sub(r"[A-Z]\d?$", "", pid)]):
        path = html_dir / f"{cand}.html"
        cached = Path(cache_dir) / f"{cand}.html" if cache_dir else None
        if path.exists():
            return path.read_text(encoding="utf-8"), cand, "cache"
        if cached and cached.exists():
            path.write_text(cached.read_text(encoding="utf-8"), encoding="utf-8")
            return path.read_text(encoding="utf-8"), cand, "cache"
        time.sleep(delay)
        r = session.get(URL.format(id=cand), timeout=60, headers={"Accept-Language": "ja"})
        if r.status_code == 200:
            r.encoding = "utf-8"
            path.write_text(r.text, encoding="utf-8")
            if cached:
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_text(r.text, encoding="utf-8")
            return r.text, cand, "200"
        status = str(r.status_code)
    return "", pid, status


def nfkc(text: str) -> str:
    """全角英数字・記号を半角に揃える(NFKC)。検索や LLM 入力での表記ゆれ対策。"""
    return unicodedata.normalize("NFKC", text)


def save_fulltext(text_dir: Path, pid: str, x: dict, source: str = "web") -> Path:
    """切り詰めなしの全文(原文と NFKC 正規化)を JSON で保存する。

    source: "web"(Google Patents の本文) / "csv_abstract"(Web から取れず、CSV の要約だけ)。評価の段階で使う。
    """
    path = text_dir / f"{pid}.json"
    data = {"source": source}
    data.update({k: x[k] for k in ("title", "abstract", "claims", "description")})
    data.update({k + "_nfkc": nfkc(x[k]) for k in ("title", "abstract", "claims", "description")})
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def run(df: pd.DataFrame, html_dir: Path, delay: float = 3.0, text_dir: Path | None = None,
        cache_dir: Path | None = None) -> pd.DataFrame:
    """文献番号の表(Google Patents ID(推定) 列を持つ)から取得・抽出し、結果の表を返す。

    text_dir を渡すと、全文を JSON で保存する(Excel のセル上限で切り詰められるため、LLM 評価にはこちらを使う)。
    cache_dir を渡すと、調査をまたいで HTML を共有する(同じ特許を別の調査で再取得しない)。
    """
    html_dir = Path(html_dir)
    html_dir.mkdir(parents=True, exist_ok=True)
    text_dir = Path(text_dir) if text_dir else html_dir.parent / "text"
    text_dir.mkdir(parents=True, exist_ok=True)
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
                html, used, status = fetch(sess, pid, html_dir, delay, cache_dir)
            except requests.RequestException as e:
                html, used, status = "", pid, f"error: {type(e).__name__}"
            rec.update({"使用ID": used, "取得状況": status})
            # CSV を入力にした場合だけ、要約(CSV)の列がある。Web から本文が取れなかったときの代わりに使う。
            csv_abs = r.get("要約(CSV)")
            csv_abs = csv_abs if isinstance(csv_abs, str) else ""
            x, source = None, "web"
            if html:
                x = extract(html)
                # Web に要約がなければ、CSV の要約で補う
                if not x["abstract"] and csv_abs:
                    x["abstract"] = csv_abs
                    x["extract_status"] = extract_status(x) + " / 要約はCSVで補完"
            elif csv_abs:
                # 404 などで Web から取れない場合は、CSV の要約だけを本文として使う(請求項・明細書は空)
                x = {"title": r.get("発明の名称") or "", "abstract": csv_abs, "claims": "", "description": "",
                     "claim_count": 0, "extract_status": f"Web取得失敗({status}): CSVの要約のみ使用"}
                source = "csv_abstract"
            if x:
                rec.update({"本文の出所": "Google Patents" if source == "web" else "CSVの要約のみ",
                            "名称(Google)": x["title"], "要約": x["abstract"],
                            "請求項数": x["claim_count"], "請求項": x["claims"],
                            "明細書": x["description"], "明細書文字数": len(x["description"]),
                            "名称(正規化)": nfkc(x["title"]),
                            # 全文 JSON は、取得に使った ID(used)ではなく、一覧の ID(pid)の名前で保存する。
                            # 評価(手順3)が一覧の ID で探すため。種別コードを外した ID で取れた場合に、見つからなくなるのを防ぐ。
                            "全文ファイル": str(save_fulltext(text_dir, pid, x, source)),
                            "抽出状況": x["extract_status"]})
                # Excel のセルは約 3 万 2 千文字までなので、超える分は切り詰める(全文は JSON と HTML に残る)
                if len(x["description"]) > EXCEL_CELL_MAX:
                    rec["明細書"] = x["description"][:EXCEL_CELL_MAX]
                    rec["抽出状況"] += " / 明細書を切り詰め(全文は全文ファイル)"
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
