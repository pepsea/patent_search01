"""プログラム1: J-PlatPat「検索結果一覧(国内文献)」のコピーテキストを、重複のない表にする。

J-PlatPat の画面は JavaScript で描画されるため、保存した HTML には表が入らない。
そのため、結果一覧をコピーして貼り付けたテキスト(*.txt)、または J-PlatPat からダウンロードした CSV(*.csv)を読む。
CSV には「要約」が入っているので、Google Patents から本文が取れなかった場合の代わりに使える。

作業の流れ:
 1. parse_text      : テキストを 1 件ずつ(No. の連番を目印に)区切り、各項目に振り分ける
    parse_csv_text  : CSV を 1 行ずつ読み、同じ項目に振り分ける(要約・J-PlatPat の URL も取る)
 2. google_patent_id: 文献番号から Google Patents の ID 候補(例: JP2017080742A)を作る
 3. build_list      : フォルダ内の全 txt / csv を読み、文献番号で重複を除いた一覧(DataFrame)にまとめる
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

FI_RE = re.compile(r"^[A-HY]\d{2}[A-Z]\d+")
DATE_RE = re.compile(r"^\d{4}/\d{2}/\d{2}$")
DOC_RE = re.compile(
    r"^(?P<kind>特開|特表|再表|特許|実登|実公|実開|公開実用|登録実用|特公)"
    r"(?P<era>昭|平)?(?P<body>[\d\-/]+)$"
)
# 文献種別 -> Google Patents の種別コード（推定。B1/B2 や Y1/Y2 は判別できない）
KIND_CODE = {"特開": "A", "特表": "A", "再表": "A1", "特許": "B2",
             "実登": "U", "実開": "U", "公開実用": "U", "登録実用": "U",
             "実公": "Y2", "特公": "B2"}
STATUS_STARTS = ("審査", "特許", "（出願の）", "-", "登録", "権利", "実用", "拒絶")
HEADER_END = "FI"


@dataclass
class PatentRow:
    no: int
    doc_no: str = ""
    app_no: str = ""
    filing_date: str = ""
    publication_date: str = ""
    title: str = ""
    applicant: str = ""
    applicant_has_more: bool = False
    status: list[str] = field(default_factory=list)
    fi: list[str] = field(default_factory=list)
    fi_has_more: bool = False
    warnings: list[str] = field(default_factory=list)
    # CSV にだけある項目。Google Patents から本文が取れなかった場合の代わりに使う。
    abstract: str = ""
    jplatpat_url: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = " / ".join(self.status)
        d["fi"] = " ; ".join(self.fi)
        d["warnings"] = " ; ".join(self.warnings)
        d["google_patent_id"] = google_patent_id(self.doc_no)
        d["google_patent_url"] = (
            f"https://patents.google.com/patent/{d['google_patent_id']}/ja"
            if d["google_patent_id"] else ""
        )
        return d


# 作業: 文献番号(特開・特表・特許・実登・再表 など)を Google Patents の ID 候補に変換する。
def google_patent_id(doc_no: str) -> str:
    """文献番号から Google Patents の ID 候補を作る（種別コードは推定）。

    例: 特開2026-139649 -> JP2026139649A / 特開昭50-051518 -> JPS50051518A
    """
    m = DOC_RE.match(doc_no)
    if not m:
        return ""
    # 再表(国際出願の再公表)は特殊な形式にする。
    # 例: 再表2015/072306 -> JPWO2015072306A1, 再表92/019759 -> JPWO1992019759A1
    if m["kind"] == "再表":
        y, n = m["body"].split("/")
        y = y if len(y) == 4 else ("19" if int(y) >= 50 else "20") + y
        return f"JPWO{y}{n}A1"
    era = {"昭": "S", "平": "H", None: ""}[m["era"]]
    digits = m["body"].replace("-", "")
    return f"JP{era}{digits}{KIND_CODE[m['kind']]}"


def _is_status_line(line: str) -> bool:
    return line.startswith(STATUS_STARTS)


# 作業: コピーテキスト全体を 1 件ごとに区切って PatentRow のリストにする。
def parse_text(text: str) -> list[PatentRow]:
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if l]
    # ヘッダ（"FI" まで）を飛ばす
    try:
        start = lines.index(HEADER_END) + 1
    except ValueError:
        start = 0
    body = lines[start:]

    # レコード境界: 連番 1,2,3... と一致する数字だけの行
    # （文献番号は数字だけにならないため、連番との一致で十分に区別できる）
    starts, expect = [], 1
    for i, l in enumerate(body):
        if l.isdigit() and int(l) == expect:
            starts.append(i)
            expect += 1
    rows = []
    for k, s in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else len(body)
        chunk = body[s + 1:e]
        # 最後の 1 件だけ、末尾の著作権表示などのフッタ行を取り除く
        if k + 1 == len(starts):
            chunk = [l for l in chunk if not l.startswith(("Copyright", "(P"))]
        rows.append(_parse_record(k + 1, chunk))
    return rows


# 作業: 1 件分の行(文献番号、出願番号、日付、名称、出願人、ステータス、FI)を各項目に振り分ける。
def _parse_record(no: int, chunk: list[str]) -> PatentRow:
    r = PatentRow(no=no)
    if len(chunk) < 6:
        r.warnings.append("行数不足")
        return r
    r.doc_no, r.app_no, r.filing_date, r.publication_date, r.title, r.applicant = chunk[:6]
    rest = chunk[6:]
    if not DOC_RE.match(r.doc_no):
        r.warnings.append("文献番号の書式が未知")
    for label, v in (("出願日", r.filing_date), ("公知日", r.publication_date)):
        if not DATE_RE.match(v):
            r.warnings.append(f"{label}の書式が未知")
    # 出願人欄の「他」（FI の「他」と区別するため、FI より前にあるものだけ）
    i = 0
    if rest and rest[0] == "他":
        r.applicant_has_more = True
        i = 1
    for l in rest[i:]:
        if l == "他":
            r.fi_has_more = True
        elif FI_RE.match(l) or re.match(r"^[A-HY]\d{2}[A-Z]\d+", l):
            r.fi.append(l)
        elif _is_status_line(l) or not r.fi:
            r.status.append(l)
        else:
            r.warnings.append(f"分類不能な行: {l}")
    return r


# 作業: 1 つの txt ファイルを読んで parse_text に渡す。
def load_file(path: str | Path) -> list[PatentRow]:
    return parse_text(Path(path).read_text(encoding="utf-8"))


# ---- CSV の読み取り -------------------------------------------------------------------------------

# 作業: CSV の FI 欄(カンマ区切り)を分ける。「G01N37/00,102」のように FI の中にもカンマがあるため、
# FI の形(英字で始まる)でない部分は、直前の FI にくっつける。
def _split_fi(text: str) -> list[str]:
    out: list[str] = []
    for t in (t.strip() for t in text.split(",")):
        if not t:
            continue
        if FI_RE.match(t) or not out:
            out.append(t)
        else:
            out[-1] += "," + t
    return out


# 作業: CSV の要約から、「(57)【要約】」「（修正有）」「【選択図】…」などの付随文字を除き、読める形にする。
def _clean_abstract(text: str) -> str:
    text = re.sub(r"^\s*\(57\)\s*【要約】", "", (text or "").strip()).replace("（修正有）", "")
    lines = (re.sub(r"[ \t\u3000]+", " ", l).strip() for l in text.splitlines())
    return "\n".join(l for l in lines if l and not l.startswith("【選択図】"))


CSV_REQUIRED = ("文献番号", "出願番号", "発明の名称")


# 作業: J-PlatPat の CSV を 1 行ずつ PatentRow にする(ステージ・イベント詳細はステータスに、要約は abstract に入れる)。
def parse_csv_text(text: str) -> list[PatentRow]:
    reader = csv.DictReader(io.StringIO(text, newline=""))
    missing = [c for c in CSV_REQUIRED if c not in (reader.fieldnames or [])]
    if missing:
        raise ValueError(f"CSV の列が足りません: {missing}(見つかった列: {reader.fieldnames})")
    rows = []
    for i, d in enumerate(reader, start=1):
        doc_no = (d.get("文献番号") or "").strip()
        if not doc_no:
            continue
        r = PatentRow(
            no=i, doc_no=doc_no, app_no=(d.get("出願番号") or "").strip(),
            filing_date=(d.get("出願日") or "").strip(), publication_date=(d.get("公知日") or "").strip(),
            title=(d.get("発明の名称") or "").strip(), applicant=(d.get("出願人/権利者") or "").strip(),
            status=[x.strip() for x in (d.get("ステージ"), d.get("イベント詳細")) if x and x.strip()],
            fi=_split_fi(d.get("FI") or ""), abstract=_clean_abstract(d.get("要約") or ""),
            jplatpat_url=(d.get("文献URL") or "").strip(),
        )
        if not DOC_RE.match(doc_no):
            r.warnings.append("文献番号の書式が未知")
        for label, v in (("出願日", r.filing_date), ("公知日", r.publication_date)):
            if not DATE_RE.match(v):
                r.warnings.append(f"{label}の書式が未知")
        rows.append(r)
    return rows


# ---- フォルダ内の複数ファイルを統合し、重複を除いた一覧を作る ------------------------------------

LIST_COLUMNS = {
    "no": "No.", "doc_no": "文献番号", "app_no": "出願番号", "filing_date": "出願日",
    "publication_date": "公知日", "title": "発明の名称", "applicant": "出願人/権利者",
    "applicant_has_more": "出願人(他あり)", "status": "ステータス", "fi": "FI",
    "fi_has_more": "FI(他あり)", "google_patent_id": "Google Patents ID(推定)",
    "google_patent_url": "Google Patents URL(推定)", "warnings": "警告",
    "abstract": "要約(CSV)", "jplatpat_url": "J-PlatPat URL",
}


def read_text_file(path: Path) -> str:
    """UTF-8(BOM可)で読み、失敗したら Shift_JIS(cp932)で読む。"""
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp932"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def build_list(folder: str | Path, pattern: str | list[str] | tuple[str, ...] = "*.txt"):
    """folder 内の pattern(複数可。例: ["*.txt", "*.csv"])に合う全ファイルを読み、文献番号で重複を除いた一覧を作る。

    戻り値: (一覧 DataFrame, 報告 dict)
    - 拡張子が .csv のファイルは CSV として、それ以外はコピーしたテキストとして読む。
    - 同じ文献番号が複数のファイルにある場合は、更新日時が新しいファイルの行を採用する
      （ステータスは時間とともに変わるため）。ただし要約は、新しい行にない場合は古い行のものを残す。
      出典は「出典ファイル」列に全て残す。
    - 同じ出願番号で文献番号が異なる行(公開公報と登録公報など)は除かず、「同一出願番号の別文献」列で示す。
    """
    import pandas as pd

    patterns = [pattern] if isinstance(pattern, str) else list(pattern)
    files = sorted({f for p in patterns for f in Path(folder).glob(p)}, key=lambda p: (p.stat().st_mtime, p.name))
    if not files:
        raise FileNotFoundError(f"{folder} に {patterns} が見つかりません")
    per_file, kept, sources, conflicts = [], {}, {}, []
    # 古いファイルから順に処理し、同じ文献番号は後(=新しいファイル)の内容で上書きする
    for f in files:
        is_csv = f.suffix.lower() == ".csv"
        try:
            rows = (parse_csv_text if is_csv else parse_text)(read_text_file(f))
        except ValueError as e:  # CSV の列が違う場合など。どのファイルかを分かるようにする
            raise ValueError(f"{f.name}: {e}") from e
        per_file.append({"ファイル": f.name, "形式": "csv" if is_csv else "txt", "読み取り件数": len(rows),
                         "警告あり": sum(bool(r.warnings) for r in rows),
                         "要約あり": sum(bool(r.abstract) for r in rows)})
        for r in rows:
            old = kept.get(r.doc_no)
            if old and (old.status != r.status or old.title != r.title):
                conflicts.append({"文献番号": r.doc_no, "採用ファイル": f.name,
                                  "旧ステータス": " / ".join(old.status), "新ステータス": " / ".join(r.status)})
            if old:  # 新しい行に無い項目(CSV にだけある要約・URL)は、古い行のものを引き継ぐ
                r.abstract = r.abstract or old.abstract
                r.jplatpat_url = r.jplatpat_url or old.jplatpat_url
            kept[r.doc_no] = r
            sources.setdefault(r.doc_no, [])
            if f.name not in sources[r.doc_no]:
                sources[r.doc_no].append(f.name)
    recs = []
    for doc_no, r in kept.items():
        d = r.to_dict()
        d["source_files"] = " ; ".join(sources[doc_no])
        recs.append(d)
    df = pd.DataFrame(recs)
    same_app = df.groupby("app_no")["doc_no"].apply(list)
    df["same_app_docs"] = [" ; ".join(x for x in same_app[a] if x != d) for a, d in zip(df["app_no"], df["doc_no"])]
    df = df.sort_values("publication_date", ascending=False, kind="stable").reset_index(drop=True)
    df["no"] = range(1, len(df) + 1)
    out = df[list(LIST_COLUMNS) + ["source_files", "same_app_docs"]].rename(
        columns={**LIST_COLUMNS, "source_files": "出典ファイル", "same_app_docs": "同一出願番号の別文献"})
    total = sum(p["読み取り件数"] for p in per_file)
    report = {"files": pd.DataFrame(per_file), "total_rows": total, "unique": len(out),
              "duplicates_removed": total - len(out), "conflicts": pd.DataFrame(conflicts)}
    return out, report
