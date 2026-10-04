"""J-PlatPat「検索結果一覧(国内文献)」のコピーテキストを表に変換する。

J-PlatPat の画面は JavaScript で描画されるため、保存した HTML には表が入らない。
結果一覧をコピーして貼り付けたテキストを読み、文献番号などを取り出す。
"""

from __future__ import annotations

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


def google_patent_id(doc_no: str) -> str:
    """文献番号から Google Patents の ID 候補を作る（種別コードは推定）。

    例: 特開2026-139649 -> JP2026139649A / 特開昭50-051518 -> JPS50051518A
    """
    m = DOC_RE.match(doc_no)
    if not m:
        return ""
    if m["kind"] == "再表":  # 例: 再表2015/072306 -> JPWO2015072306A1, 再表92/019759 -> JPWO1992019759A1
        y, n = m["body"].split("/")
        y = y if len(y) == 4 else ("19" if int(y) >= 50 else "20") + y
        return f"JPWO{y}{n}A1"
    era = {"昭": "S", "平": "H", None: ""}[m["era"]]
    digits = m["body"].replace("-", "")
    return f"JP{era}{digits}{KIND_CODE[m['kind']]}"


def _is_status_line(line: str) -> bool:
    return line.startswith(STATUS_STARTS)


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
        if k + 1 == len(starts):  # 末尾のフッタを除去
            chunk = [l for l in chunk if not l.startswith(("Copyright", "(P"))]
        rows.append(_parse_record(k + 1, chunk))
    return rows


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


def load_file(path: str | Path) -> list[PatentRow]:
    return parse_text(Path(path).read_text(encoding="utf-8"))
