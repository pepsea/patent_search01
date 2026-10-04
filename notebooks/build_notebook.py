"""notebooks/patent_pipeline.ipynb を patent_search/ のソースから生成する（ソースとの食い違いを防ぐ）。"""
import re
from pathlib import Path

import nbformat as nbf

root = Path(__file__).resolve().parents[1]
platpat = (root / "patent_search/platpat.py").read_text(encoding="utf-8")
fetch_src = (root / "patent_search/fetch_google.py").read_text(encoding="utf-8")
fetch_src = fetch_src[: fetch_src.index("def main()")].rstrip() + "\n"

md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
cells = [
    md("# 特許調査パイプライン（ステップ1・2）\n"
       "1. J-PlatPat の検索結果一覧（コピーしたテキスト）から文献番号表を作る\n"
       "2. 文献番号から Google Patents（日本語ページ）の HTML を取得し、名称・要約・請求項・明細書を Excel に出力する\n\n"
       "**使い方**: 上から順に実行。まず設定セルの値を変更し、手順2は `LIMIT = 3` などで少数件を試してから全件にしてください。\n\n"
       "注意: Google Patents の自動取得は利用規約上の制限を受け得ます。`DELAY` を空けて、必要な件数だけ実行してください。"),
    code("%pip install -q pandas openpyxl requests beautifulsoup4 lxml"),
    md("## 設定"),
    code('from pathlib import Path\n\n'
         'INPUT_TXT = "patent_data1.txt"          # J-PlatPat 結果一覧のコピーテキスト\n'
         'NUMBERS_XLSX = "results/patent_numbers.xlsx"   # 手順1の出力\n'
         'RESULT_XLSX = "results/patents_text.xlsx"      # 手順2の出力\n'
         'HTML_DIR = "results/html"               # 取得した生 HTML の保存先（再実行時は取得済みを飛ばす）\n'
         'LIMIT = 3                               # 手順2で処理する件数。None なら全件\n'
         'DELAY = 3.0                             # 取得間隔(秒)\n\n'
         'Path("results").mkdir(exist_ok=True)'),
    md("## 手順1: 文献番号の抽出（コード）"),
    code(platpat),
    md("## 手順1: 実行"),
    code('import pandas as pd\n\n'
         'rows = load_file(INPUT_TXT)\n'
         'COLUMNS = {\n'
         '    "no": "No.", "doc_no": "文献番号", "app_no": "出願番号", "filing_date": "出願日",\n'
         '    "publication_date": "公知日", "title": "発明の名称", "applicant": "出願人/権利者",\n'
         '    "applicant_has_more": "出願人(他あり)", "status": "ステータス", "fi": "FI",\n'
         '    "fi_has_more": "FI(他あり)", "google_patent_id": "Google Patents ID(推定)",\n'
         '    "google_patent_url": "Google Patents URL(推定)", "warnings": "警告",\n'
         '}\n'
         'numbers = pd.DataFrame([r.to_dict() for r in rows])[list(COLUMNS)].rename(columns=COLUMNS)\n'
         'numbers.to_excel(NUMBERS_XLSX, index=False)\n'
         'print(f"{len(numbers)} 件 -> {NUMBERS_XLSX} / 警告あり {int((numbers[\'警告\'] != \'\').sum())} 件")\n'
         'numbers.head(10)'),
    code("numbers[numbers['警告'] != ''][['No.', '文献番号', '警告']]  # 読み取れなかった行（空なら問題なし）"),
    md("## 手順2: Google Patents から取得・抽出（コード）"),
    code(fetch_src),
    md("## 手順2: 実行\nまず `LIMIT = 3` 程度で、取得状況・抽出状況を確認してください。"),
    code("targets = numbers if LIMIT is None else numbers.head(LIMIT)\n"
         "result = run(targets, Path(HTML_DIR), DELAY)\n"
         "result.to_excel(RESULT_XLSX, index=False)\n"
         "print('->', RESULT_XLSX)\n"
         "result[[c for c in ['文献番号', 'ID', '使用ID', '取得状況', '抽出状況', '請求項数'] if c in result]]"),
    md("取得状況が `200`/`cache` 以外、または抽出状況が `OK` 以外の行を確認します。"),
    code("result[(result['取得状況'].isin(['200', 'cache']) == False) | (result.get('抽出状況', 'OK') != 'OK')]"),
]
nb = nbf.v4.new_notebook(cells=cells)
nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
nbf.write(nb, root / "notebooks/patent_pipeline.ipynb")
print("written")
