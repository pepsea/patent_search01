"""J-PlatPat の結果一覧テキストから文献番号表を作る: python -m patent_search.extract_numbers IN.txt OUT.xlsx"""

import sys

import pandas as pd

from .platpat import load_file

COLUMNS = {
    "no": "No.", "doc_no": "文献番号", "app_no": "出願番号", "filing_date": "出願日",
    "publication_date": "公知日", "title": "発明の名称", "applicant": "出願人/権利者",
    "applicant_has_more": "出願人(他あり)", "status": "ステータス", "fi": "FI",
    "fi_has_more": "FI(他あり)", "google_patent_id": "Google Patents ID(推定)",
    "google_patent_url": "Google Patents URL(推定)", "warnings": "警告",
}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    rows = load_file(argv[0])
    df = pd.DataFrame([r.to_dict() for r in rows])[list(COLUMNS)].rename(columns=COLUMNS)
    with pd.ExcelWriter(argv[1], engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="一覧")
        ws = w.sheets["一覧"]
        ws.freeze_panes = "A2"
        for col, width in zip("ABCDEFGHIJKLMN", (6, 18, 16, 12, 12, 50, 30, 8, 26, 30, 8, 24, 50, 20)):
            ws.column_dimensions[col].width = width
    print(f"{len(df)} 件 -> {argv[1]}  / 警告あり {int((df['警告'] != '').sum())} 件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
