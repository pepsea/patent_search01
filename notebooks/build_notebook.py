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

# ================= 手順1・2 の設定 =================

# J-PlatPat の結果一覧をコピーした txt を入れたフォルダ。複数ファイルを置くと、まとめて読み込んで重複を除く。
INPUT_DIR = "../data"
# フォルダ内で読み込むファイルの名前の形。
INPUT_PATTERN = "*.txt"
# 手順1の出力: 重複を除いた文献番号の一覧(Excel)。
NUMBERS_XLSX = "results/patent_numbers.xlsx"
# 手順2の出力: 名称・要約・請求項・明細書の表(Excel)。
RESULT_XLSX = "results/patents_text.xlsx"
# 取得した生の HTML の保存先。再実行時は、ここにあるものは取得し直さない。
HTML_DIR = "results/html"
# 全文 JSON の保存先。Excel は約3万字で切れるため、LLM 評価にはこちらを使う。
TEXT_DIR = "results/text"
# 手順2で処理する件数。まず 3 で試し、問題なければ None(全件)にする。
LIMIT = 3
# Google Patents へのアクセス間隔(秒)。短くしすぎない。
DELAY = 3.0

# ================= 手順3 の設定: 調べたいこと（ここを書き換える。プロンプトにそのまま組み込まれる）=================

# テーマの名前。結果の表やプロンプトに表示される。
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

# 関連とみなす条件（任意）。判断が分かれる境界を文章で決めておく。
TOPIC_INCLUDE = """
total RNA-seq、rRNA除去を伴うRNA-seq、非コードRNAや前駆体RNAも含めた網羅的RNA配列解析の
手法・キット・データ解析方法。それらを実施例で実際に使っている特許も含める。
"""

# 関連とみなさない条件（任意）。
TOPIC_EXCLUDE = """
poly(A)選択によるmRNA-seqのみを扱い、total RNAやrRNA除去に触れないもの。
RNAを単に治療薬の成分として扱うもの（核酸医薬、mRNAワクチンなど）で、RNA-seq解析を含まないもの。
"""

# ================= 手順3 の設定: LLM =================

# 使う LLM の方式。"ollama"(この PC) または "guidance"(サーバー: Hugging Face のモデル)。
BACKEND = "ollama"
# Ollama のモデル名。ollama list で表示される名前。
OLLAMA_MODEL = "qwen3:14b"
# Ollama が一度に読める長さ。大きいと遅くメモリも使う。MAX_CHARS に合わせる。
OLLAMA_NUM_CTX = 8192
# guidance 用の Hugging Face のモデル ID。サーバーでは使うモデルに変更する。
HF_MODEL_ID = "Qwen/Qwen3-14B"
# 1件あたり LLM に渡す本文の最大文字数（請求項と明細書で半分ずつ）。
MAX_CHARS = 6000
# 手順3で評価する件数。まず 3 で試し、問題なければ None(全件)にする。
EVAL_LIMIT = 3
# 手順3の出力: 関連性の評価結果(Excel)。文献番号は Google Patents へのリンクになる。
RESULT_EVAL_XLSX = "results/evaluation.xlsx"

# 出願企業の表示名を統一する対応表。{正規化した名前: 表示名}。
# 正規化した名前は、全角半角をそろえ、空白・中黒と「株式会社」「インコーポレイテッド」等の法人格を除いたもの。
# 例: "エルジー　エレクトロニクス　インコーポレイティド" -> "エルジーエレクトロニクス"。必要に応じて追加する。
COMPANY_ALIASES = {
    "三星電子": "Samsung Electronics",
    "三星エスディアイ": "Samsung SDI",
    "エルジーエレクトロニクス": "LG Electronics",
    "エルジーエナジーソリューション": "LG Energy Solution",
    "エルジーケム": "LG Chem",
    "エルジーディスプレイ": "LG Display",
    "シェイプコープ": "Shape Corp.",
}

# 出力先フォルダを作る(すでにあれば何もしない)。
Path("results").mkdir(exist_ok=True)'''

STEP1_RUN = '''import pandas as pd

# フォルダ内の全 txt を読み、文献番号で重複を除いた一覧(numbers)と、読み込みの報告(report)を作る。
numbers, report = build_list(INPUT_DIR, INPUT_PATTERN)
# 一覧を Excel に保存する。
numbers.to_excel(NUMBERS_XLSX, index=False)
# 件数の内訳を表示する。
print(f"読み取り合計 {report['total_rows']} 件 -> 重複除去後 {report['unique']} 件（除去 {report['duplicates_removed']} 件）-> {NUMBERS_XLSX}")
# ファイルごとの読み取り件数を表示する。0件のファイルは、書式が違う可能性がある。
report["files"]'''

BACKEND_CELL = '''# 設定の BACKEND に応じて、LLM に問い合わせる関数(backend)を用意する。
if BACKEND == "ollama":
    backend = ollama_backend(OLLAMA_MODEL, num_ctx=OLLAMA_NUM_CTX)
elif BACKEND == "guidance":
    from guidance import models
    backend = guidance_backend(models.Transformers(HF_MODEL_ID, device_map="auto"))
else:
    raise ValueError(BACKEND)
# 設定の「調べたいこと」を 1 つにまとめる。
topic = Topic(TOPIC_NAME, TOPIC_DEFINITION, TOPIC_KEYWORDS, TOPIC_INCLUDE, TOPIC_EXCLUDE)
# 手順2で保存した全文 JSON のうち、1 件目をプロンプトの見本に使う。
sample = next(Path(TEXT_DIR).glob("*.json"))
prompt, _ = build_prompt(topic, "（例）" + sample.stem, json.loads(sample.read_text(encoding="utf-8")), MAX_CHARS)
# LLM に実際に渡る文章を表示する(内容を目で確認する)。
print(prompt)'''

STEP2_RUN = """# LIMIT が None なら全件、数字ならその件数だけを対象にする。
targets = numbers if LIMIT is None else numbers.head(LIMIT)
# 取得・抽出を実行し、結果の表を受け取る。
result = run(targets, Path(HTML_DIR), DELAY, Path(TEXT_DIR))
# 結果を Excel に保存する。
result.to_excel(RESULT_XLSX, index=False)
print('->', RESULT_XLSX)
# 取得状況・抽出状況などの要点だけを表示する。
result[[c for c in ['文献番号', 'ID', '使用ID', '取得状況', '抽出状況', '請求項数'] if c in result]]"""

STEP3_RUN = """# EVAL_LIMIT が None なら全件、数字ならその件数だけを対象にする。
targets3 = numbers if EVAL_LIMIT is None else numbers.head(EVAL_LIMIT)
# LLM で 1 件ずつ評価し、結果の表を受け取る。
evaluation = evaluate_table(backend, topic, targets3, TEXT_DIR, MAX_CHARS, COMPANY_ALIASES)
# 結果を Excel に保存する(文献番号をクリックで Google Patents が開く。列と順番は固定)。
save_evaluation_excel(evaluation, RESULT_EVAL_XLSX)
print('->', RESULT_EVAL_XLSX)
# 結果の表を画面に表示する(リンク列は Excel 側でだけ使うので除く)。
evaluation.drop(columns=["リンク"])"""

md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell


def explain(n, title, work, inp, out):
    """各コードセルの直前に置く説明(作業・入力・出力)。"""
    return md(f"### セル{n}: {title}\n- **作業**: {work}\n- **入力**: {inp}\n- **出力**: {out}")


cells = [
    md("# 特許調査パイプライン（ステップ1〜3）\n"
       "1. 指定フォルダ内の J-PlatPat 検索結果一覧（コピーしたテキスト、複数可）を統合し、重複を除いた文献番号表を作る\n"
       "2. 文献番号から Google Patents（日本語ページ）の HTML を取得し、名称・要約・請求項・明細書を Excel に出力する\n"
       "3. ローカル LLM で、各特許が「調べたいこと」に関連するかを評価して表にする\n\n"
       "**使い方**: 上から順に実行。まず設定セルの値を変更し、手順2・3は `LIMIT` / `EVAL_LIMIT = 3` などで少数件を試してから全件にしてください。\n\n"
       "**各セルの説明は、そのセルの上にあります。** プログラム本体のセル（セル3・8・11）は、先頭にそのプログラムの作業の流れが書いてあります。\n\n"
       "注意: Google Patents の自動取得は利用規約上の制限を受け得ます。`DELAY` を空けて、必要な件数だけ実行してください。"),

    explain(1, "ライブラリの準備",
            "必要な Python ライブラリ(表計算・Excel 出力・通信・HTML 解析)を入れる。入っていれば何もしない",
            "なし", "なし(ライブラリが使える状態になる)"),
    code("%pip install -q pandas openpyxl requests beautifulsoup4 lxml"),

    explain(2, "設定（調べたいことはここに書く）",
            "フォルダ・出力先・件数などの設定と、手順3の「調べたいこと」、使う LLM を決める。各設定の上にその意味を書いてある",
            "あなたが書き換える値", "なし(以降のセルが、ここの値を使う)"),
    code(SETTINGS),

    md("## 手順1: 文献番号の一覧を作る"),
    explain(3, "プログラム1: テキストの読み取り",
            "J-PlatPat の結果一覧テキストを 1 件ずつに区切り、文献番号・出願番号・日付・名称・出願人・ステータス・FI に振り分ける。"
            "フォルダ内の複数ファイルをまとめ、文献番号で重複を除く。Google Patents の ID 候補も作る",
            "なし(関数を定義するだけ)", "なし(次のセルで使う関数 parse_text・build_list などができる)"),
    code(platpat),
    explain(4, "手順1の実行: 一覧の作成",
            "設定したフォルダの全 txt を読み、重複を除いた文献番号の一覧を作って Excel に保存する",
            "設定の INPUT_DIR 内の txt", "numbers(一覧)、report(報告)、results/patent_numbers.xlsx"),
    code(STEP1_RUN),
    explain(5, "確認: ファイル間で内容が違った行",
            "同じ文献番号でファイル間にステータス等の違いがあった行を表示する。新しいファイルの内容を採用済み",
            "report", "表(空なら該当なし)"),
    code("report['conflicts']"),
    explain(6, "確認: 読み取れなかった行",
            "文献番号や日付の書式が想定と違い、読み取りに警告が出た行を表示する",
            "numbers", "表(空なら問題なし)"),
    code("numbers[numbers['警告'] != ''][['No.', '文献番号', '警告']]"),
    explain(7, "確認: 同じ出願番号で別の文献番号の行",
            "同じ出願番号で文献番号が違う行(公開公報と登録公報など)を表示する。除外はしていないので、重複評価を避けたい場合の参考にする",
            "numbers", "表"),
    code("numbers[numbers['同一出願番号の別文献'] != ''][['文献番号', '出願番号', '同一出願番号の別文献']]"),

    md("## 手順2: Google Patents から本文を取得する"),
    explain(8, "プログラム2: HTML の取得と本文の抽出",
            "文献番号から Google Patents の日本語ページの HTML を取得して保存し、名称・要約・請求項・明細書を取り出す。"
            "全文は切り詰めずに JSON でも保存する(原文と、全角を半角に揃えた版)",
            "なし(関数を定義するだけ)", "なし(次のセルで使う関数 run などができる)"),
    code(fetch_src),
    explain(9, "手順2の実行: 取得と抽出",
            "一覧の先頭から LIMIT 件について、HTML を取得し本文を抽出して Excel に保存する。取得済みの HTML は再利用する",
            "numbers、設定の LIMIT・DELAY", "result(表)、results/patents_text.xlsx、results/html/、results/text/"),
    code(STEP2_RUN),
    explain(10, "確認: 取得・抽出に失敗した行",
            "取得状況が 200 / cache 以外、または抽出状況が OK 以外の行を表示する",
            "result", "表(空なら全件成功)"),
    code("result[(result['取得状況'].isin(['200', 'cache']) == False) | (result.get('抽出状況', 'OK') != 'OK')]"),

    md("## 手順3: LLM による関連性の評価"),
    explain(11, "プログラム3: 関連性の評価",
            "調べたいことの関連語の周辺を本文から抜粋し、判定基準と一緒に LLM へのプロンプトを作って判定させる。"
            "判定は JSON の形式に制約され、「根拠の引用」が原文に実在するかも自動で確認する",
            "なし(関数を定義するだけ)", "なし(次の 2 つのセルで使う関数ができる)"),
    code(evaluate_src),
    explain(12, "LLM の準備とプロンプトの確認",
            "設定の BACKEND に応じて LLM に問い合わせる準備をし、調べたいことをまとめ、実際に LLM に渡る文章(プロンプト)の見本を表示する。"
            "ollama は Ollama の起動と `ollama pull qwen3:14b` 済みであること。"
            "guidance は `pip install guidance transformers torch accelerate` が必要で、モデルは初回に Hugging Face から取得される",
            "設定の BACKEND・TOPIC_*、results/text/ の全文 JSON", "backend、topic、プロンプトの見本(画面表示)"),
    code(BACKEND_CELL),
    explain(13, "手順3の実行: 評価",
            "一覧の先頭から EVAL_LIMIT 件を LLM で評価し、関連度の高い順の Excel にする。列は、文献番号(Google Patents へのリンク)、判定、関連度、関連語ヒット数、理由、引用の検証、根拠の引用、発明の名称、出願人・権利者、出願企業、ステータス、発明内容概要",
            "numbers、results/text/ の全文 JSON、backend、topic", "evaluation(表)、results/evaluation.xlsx"),
    code(STEP3_RUN),
]
nb = nbf.v4.new_notebook(cells=cells)
nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
nbf.write(nb, root / "notebooks/patent_pipeline.ipynb")
print("written")
