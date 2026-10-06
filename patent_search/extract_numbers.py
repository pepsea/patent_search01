"""J-PlatPat の結果一覧テキスト(1ファイルまたはフォルダ)から、重複を除いた文献番号表を作る:
python -m patent_search.extract_numbers IN.txt|IN_DIR OUT.xlsx"""

import sys
from pathlib import Path

from .platpat import build_list


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    src = Path(argv[0])
    df, rep = build_list(src.parent if src.is_file() else src, src.name if src.is_file() else "*.txt")
    with __import__("pandas").ExcelWriter(argv[1], engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="一覧")
        ws = w.sheets["一覧"]
        ws.freeze_panes = "A2"
    print(rep["files"].to_string(index=False))
    print(f"読み取り合計 {rep['total_rows']} 件 -> 重複除去後 {rep['unique']} 件（除去 {rep['duplicates_removed']} 件）-> {argv[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
