"""notebooks/patent_pipeline.ipynb を patent_search/ のソースから生成する（ソースとの食い違いを防ぐ）。"""
from pathlib import Path

import nbformat as nbf

root = Path(__file__).resolve().parents[1]
platpat = (root / "patent_search/platpat.py").read_text(encoding="utf-8")
evaluate_src = (root / "patent_search/evaluate.py").read_text(encoding="utf-8")
fetch_src = (root / "patent_search/fetch_google.py").read_text(encoding="utf-8")
fetch_src = fetch_src[: fetch_src.index("def main()")].rstrip() + "\n"

SETTINGS = '''from pathlib import Path
import json

# ================= 手順1・2 =================
INPUT_DIR = "../data"                   # J-PlatPat 結果一覧のコピーテキスト(*.txt)を入れたフォルダ。複数可
INPUT_PATTERN = "*.txt"
NUMBERS_XLSX = "results/patent_numbers.xlsx"   # 手順1の出力
RESULT_XLSX = "results/patents_text.xlsx"      # 手順2の出力
HTML_DIR = "results/html"               # 取得した生 HTML の保存先（再実行時は取得済みを飛ばす）
TEXT_DIR = "results/text"               # 全文JSONの保存先（Excelは約3万字で切れるため、LLM評価にはこちらを使う）
LIMIT = 3                               # 手順2で処理する件数。None なら全件
DELAY = 3.0                             # 取得間隔(秒)

# ================= 手順3: 調べたいこと（ここを書き換える。プロンプトにそのまま組み込まれる）=================
TOPIC_NAME = "TOTAL-RNA-seq"

# 何を指すテーマか。専門外の人にも通じる文章で、手法・対象・範囲を定義する。
TOPIC_DEFINITION = """
TOTAL-RNA-seq（全RNAシーケンシング）とは、poly(A)選択でmRNAだけを濃縮するのではなく、
rRNA除去（rRNA depletion / ribo-depletion）などによって、mRNAに加えてlncRNA・非ポリA RNA・
前駆体RNAなどを含む全RNAを対象にライブラリを作製し、次世代シーケンサーで読み取る手法をいう。
"""

# 同義語・日英表記・商品名。本文中の出現箇所を抜粋してLLMに渡す（網羅的なほど拾いやすい）。
TOPIC_KEYWORDS = [
    "total RNA-seq", "total RNA sequencing", "total RNA", "whole transcriptome sequencing",
    "rRNA depletion", "ribosomal RNA depletion", "ribo-depletion", "Ribo-Zero", "RiboMinus",
    "全RNA", "トータルRNA", "全トランスクリプトーム", "rRNA除去", "リボソームRNA除去",
]

# 関連とみなす条件 / みなさない条件（任意）。判断が分かれる境界を文章で決めておく。
TOPIC_INCLUDE = """
total RNA-seq、rRNA除去を伴うRNA-seq、非コードRNAや前駆体RNAも含めた網羅的RNA配列解析の
手法・キット・データ解析方法。それらを実施例で実際に使っている特許も含める。
"""
TOPIC_EXCLUDE = """
poly(A)選択によるmRNA-seqのみを扱い、total RNAやrRNA除去に触れないもの。
RNAを単に治療薬の成分として扱うもの（核酸医薬、mRNAワクチンなど）で、RNA-seq解析を含まないもの。
"""

# ================= 手順3: LLM バックエンド =================
BACKEND = "ollama"                      # "ollama"（この PC）または "guidance"（サーバー: Hugging Face モデル）
OLLAMA_MODEL = "qwen3:14b"              # ollama list で表示される名前
OLLAMA_NUM_CTX = 8192                   # 大きいと遅くメモリも使う。MAX_CHARS に合わせる
HF_MODEL_ID = "Qwen/Qwen3-14B"          # guidance 用（サーバーでは使うモデルに変更）
MAX_CHARS = 6000                        # 1件あたりLLMに渡す本文の最大文字数（請求項と明細書で半分ずつ）
EVAL_LIMIT = 3                          # 手順3で評価する件数。None なら全件
RESULT_EVAL_XLSX = "results/evaluation.xlsx"   # 手順3の出力

Path("results").mkdir(exist_ok=True)'''

STEP1_RUN = '''import pandas as pd

numbers, report = build_list(INPUT_DIR, INPUT_PATTERN)
numbers.to_excel(NUMBERS_XLSX, index=False)
print(f"読み取り合計 {report['total_rows']} 件 -> 重複除去後 {report['unique']} 件（除去 {report['duplicates_removed']} 件）-> {NUMBERS_XLSX}")
report["files"]  # ファイルごとの読み取り件数（0件のファイルは書式が違う可能性）'''

BACKEND_CELL = '''if BACKEND == "ollama":
    backend = ollama_backend(OLLAMA_MODEL, num_ctx=OLLAMA_NUM_CTX)
elif BACKEND == "guidance":
    from guidance import models
    backend = guidance_backend(models.Transformers(HF_MODEL_ID, device_map="auto"))
else:
    raise ValueError(BACKEND)
topic = Topic(TOPIC_NAME, TOPIC_DEFINITION, TOPIC_KEYWORDS, TOPIC_INCLUDE, TOPIC_EXCLUDE)
sample = next(Path(TEXT_DIR).glob("*.json"))
prompt, _ = build_prompt(topic, "（例）" + sample.stem, json.loads(sample.read_text(encoding="utf-8")), MAX_CHARS)
print(prompt)  # LLM に渡る実際のプロンプト（本文は1件目の例）'''

md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
cells = [
    md("# 特許調査パイプライン（ステップ1〜3）\n"
       "1. 指定フォルダ内の J-PlatPat 検索結果一覧（コピーしたテキスト、複数可）を統合し、重複を除いた文献番号表を作る\n"
       "2. 文献番号から Google Patents（日本語ページ）の HTML を取得し、名称・要約・請求項・明細書を Excel に出力する\n"
       "3. ローカル LLM で、各特許が「調べたいこと」に関連するかを評価して表にする\n\n"
       "**使い方**: 上から順に実行。まず設定セルの値を変更し、手順2・3は `LIMIT` / `EVAL_LIMIT = 3` などで少数件を試してから全件にしてください。\n\n"
       "注意: Google Patents の自動取得は利用規約上の制限を受け得ます。`DELAY` を空けて、必要な件数だけ実行してください。"),
    code("%pip install -q pandas openpyxl requests beautifulsoup4 lxml"),
    md("## 設定（調べたいことはここに書く）"),
    code(SETTINGS),
    md("## 手順1: 文献番号の抽出（コード）"),
    code(platpat),
    md("## 手順1: 実行"),
    code(STEP1_RUN),
    md("同じ文献番号でファイル間に内容の違い（ステータス更新など）があった行です。新しいファイルの内容を採用しています。"),
    code("report['conflicts']"),
    md("読み取れなかった行（空なら問題なし）と、同じ出願番号で文献番号が違う行（公開公報と登録公報など。除外はしていません）。"),
    code("numbers[numbers['警告'] != ''][['No.', '文献番号', '警告']]"),
    code("numbers[numbers['同一出願番号の別文献'] != ''][['文献番号', '出願番号', '同一出願番号の別文献']]"),
    md("## 手順2: Google Patents から取得・抽出（コード）"),
    code(fetch_src),
    md("## 手順2: 実行\nまず `LIMIT = 3` 程度で、取得状況・抽出状況を確認してください。"),
    code("targets = numbers if LIMIT is None else numbers.head(LIMIT)\n"
         "result = run(targets, Path(HTML_DIR), DELAY, Path(TEXT_DIR))\n"
         "result.to_excel(RESULT_XLSX, index=False)\n"
         "print('->', RESULT_XLSX)\n"
         "result[[c for c in ['文献番号', 'ID', '使用ID', '取得状況', '抽出状況', '請求項数'] if c in result]]"),
    md("取得状況が `200`/`cache` 以外、または抽出状況が `OK` 以外の行を確認します。"),
    code("result[(result['取得状況'].isin(['200', 'cache']) == False) | (result.get('抽出状況', 'OK') != 'OK')]"),
    md("## 手順3: LLM による関連性評価（コード）\n"
       "判定は JSON スキーマで制約されます。`根拠の引用` が本当に原文にあるかも自動で確認します（`引用の検証` 列）。"),
    code(evaluate_src),
    md("## 手順3: バックエンドの準備\n"
       "- `ollama`: Ollama を起動し、`ollama pull qwen3:14b` 済みであること。\n"
       "- `guidance`: `pip install guidance transformers torch accelerate` が必要。モデルは初回に Hugging Face から取得されます。"),
    code(BACKEND_CELL),
    md("## 手順3: 実行\nまず `EVAL_LIMIT = 3` で結果を目視確認してから、全件にしてください。"),
    code("targets3 = numbers if EVAL_LIMIT is None else numbers.head(EVAL_LIMIT)\n"
         "evaluation = evaluate_table(backend, topic, targets3, TEXT_DIR, MAX_CHARS)\n"
         "evaluation.to_excel(RESULT_EVAL_XLSX, index=False)\n"
         "print('->', RESULT_EVAL_XLSX)\n"
         "evaluation"),
]
nb = nbf.v4.new_notebook(cells=cells)
nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
nbf.write(nb, root / "notebooks/patent_pipeline.ipynb")
print("written")
