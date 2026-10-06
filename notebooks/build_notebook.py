"""notebooks/patent_pipeline.ipynb を patent_search/ のソースから生成する（ソースとの食い違いを防ぐ）。"""
from pathlib import Path

import nbformat as nbf

root = Path(__file__).resolve().parents[1]
platpat = (root / "patent_search/platpat.py").read_text(encoding="utf-8")
runs_src = (root / "patent_search/runs.py").read_text(encoding="utf-8")
evaluate_src = (root / "patent_search/evaluate.py").read_text(encoding="utf-8")
fetch_src = (root / "patent_search/fetch_google.py").read_text(encoding="utf-8")
fetch_src = fetch_src[: fetch_src.index("def main()")].rstrip() + "\n"

SETTINGS = '''from pathlib import Path
import json

# ================= 手順1・2 の設定 =================

# J-PlatPat の結果(txt または csv)を入れたフォルダ。複数ファイルを置くと、まとめて読み込んで重複を除く。
INPUT_DIR = "../data"
# 入力の形式。"txt"(結果一覧をコピーしたテキスト)、"csv"(J-PlatPat からダウンロードした CSV)、"both"(両方)から選ぶ。
# csv には「要約」が入っている。Google Patents から本文が取れなかった(404 など)場合に、この要約を代わりに使う。
INPUT_FORMAT = "txt"
# 結果を入れる大元のフォルダ。この中に「トピック名_日時」の調査フォルダが作られる。
RESULTS_ROOT = "results"
# None なら、実行のたびに新しい調査フォルダを作る。途中から続ける場合は、既存のフォルダ名を指定する。
# 例: "TOTAL-RNA-seq_20261004_153005"
RUN_DIR = None
# 取得した HTML を調査をまたいで共有する場所。同じ特許を別の調査で、Google に取りに行かないために使う。
CACHE_DIR = "results/_html_cache"
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
# Ollama の返答の受け取り方。"none"(構造化出力を使わず、プロンプトで JSON を指示し、読めなければやり直す)、
# "json"(Ollama の JSON モード)、"schema"(Ollama の構造化出力)から選ぶ。
# 返答が文字化けする場合は "none" を使う。原因の切り分けは、最後の「文字化けの診断」セルで行う。
OLLAMA_FORMAT = "none"
# Ollama が一度に読める長さ。大きいと遅くメモリも使う。MAX_CHARS に合わせる。
OLLAMA_NUM_CTX = 8192
# guidance 用の Hugging Face のモデル ID。サーバーでは使うモデルに変更する。
HF_MODEL_ID = "Qwen/Qwen3-14B"
# 1件あたり LLM に渡す本文の最大文字数（請求項と明細書で半分ずつ）。
MAX_CHARS = 6000
# True なら、手順3で LLM が生成している様子を、画面にリアルタイムで表示する。
STREAM = True
# 手順3の直前に、LLM に渡るプロンプトを確認する特許の文献番号(例: "特開2011-204261")。
# None なら、全文 JSON がある先頭の 1 件。
PREVIEW_DOC = None
# 手順3で評価する件数。まず 3 で試し、問題なければ None(全件)にする。
EVAL_LIMIT = 3

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

# 入力の形式から、読み込むファイルの名前の形を決める。
INPUT_PATTERNS = {"txt": ["*.txt"], "csv": ["*.csv"], "both": ["*.txt", "*.csv"]}[INPUT_FORMAT]

# 大元のフォルダを作る(すでにあれば何もしない)。
Path(RESULTS_ROOT).mkdir(exist_ok=True)'''

RUN_CELL = '''# 調査フォルダ「トピック名_日時」を作る(RUN_DIR を指定した場合は、その既存フォルダを使う)。
# 同じ起動中にこのセルを再実行した場合(RUN_DIR が None で、同じトピックの調査フォルダが直前にできている場合)は、
# 新しい空のフォルダを作らず、直前のフォルダを続けて使う。新しく作り直したい場合は、カーネルを再起動する。
if RUN_DIR is None and "run_dir" in globals() and Path(run_dir).is_dir() and Path(run_dir).name.startswith(safe_name(TOPIC_NAME) + "_"):
    print("直前の調査フォルダを続けて使います(新しく作る場合は、カーネルを再起動してください)")
else:
    run_dir = make_run_dir(RESULTS_ROOT, TOPIC_NAME, RUN_DIR)
# 入力のファイル(txt / csv)を、調査フォルダの input/ にコピーして残す。
copied = register_inputs(run_dir, INPUT_DIR, INPUT_PATTERNS)
# 以降のセルが使う出力先を、すべて調査フォルダの中に決める(ファイル名にトピック名は使わない)。
NUMBERS_XLSX = run_file(run_dir, "patent_numbers")
RESULT_XLSX = run_file(run_dir, "patents_text")
HTML_DIR = run_dir / "html"
TEXT_DIR = run_dir / "text"
RESULT_EVAL_XLSX = run_file(run_dir, "evaluation")
# 今回の設定を run_settings.json に保存する(後から、何を調べたかを確認できる)。
save_run_settings(run_dir, {
    "トピック名": TOPIC_NAME, "定義": TOPIC_DEFINITION, "関連語": TOPIC_KEYWORDS,
    "含める条件": TOPIC_INCLUDE, "除外する条件": TOPIC_EXCLUDE,
    "LLM方式": BACKEND, "モデル": OLLAMA_MODEL if BACKEND == "ollama" else HF_MODEL_ID,
    "num_ctx": OLLAMA_NUM_CTX, "Ollamaの返答方式": OLLAMA_FORMAT, "本文の最大文字数": MAX_CHARS, "取得件数(LIMIT)": LIMIT, "評価件数(EVAL_LIMIT)": EVAL_LIMIT,
    "取得間隔(秒)": DELAY, "入力フォルダ": INPUT_DIR, "入力形式": INPUT_FORMAT, "入力ファイル": copied, "出願企業の別名": COMPANY_ALIASES,
})
print("調査フォルダ:", run_dir)'''

STEP1_RUN = '''import pandas as pd

# フォルダ内の全ファイル(txt / csv)を読み、文献番号で重複を除いた一覧(numbers)と、読み込みの報告(report)を作る。
numbers, report = build_list(INPUT_DIR, INPUT_PATTERNS)
# 一覧を Excel に保存する。
numbers.to_excel(NUMBERS_XLSX, index=False)
# 件数の内訳を表示する。
print(f"読み取り合計 {report['total_rows']} 件 -> 重複除去後 {report['unique']} 件（除去 {report['duplicates_removed']} 件）-> {NUMBERS_XLSX}")
# ファイルごとの読み取り件数を表示する。0件のファイルは、書式が違う可能性がある。
report["files"]'''

BACKEND_CELL = '''# 設定の BACKEND に応じて、LLM に問い合わせる関数(backend)を用意する。
if BACKEND == "ollama":
    backend = ollama_backend(OLLAMA_MODEL, num_ctx=OLLAMA_NUM_CTX, mode=OLLAMA_FORMAT)
elif BACKEND == "guidance":
    from guidance import models
    backend = guidance_backend(models.Transformers(HF_MODEL_ID, device_map="auto"))
else:
    raise ValueError(BACKEND)
# 設定の「調べたいこと」を 1 つにまとめる。
topic = Topic(TOPIC_NAME, TOPIC_DEFINITION, TOPIC_KEYWORDS, TOPIC_INCLUDE, TOPIC_EXCLUDE)

# プロンプトを確認する特許を選ぶ。PREVIEW_DOC が None なら、全文 JSON がある先頭の 1 件。
candidates = numbers if PREVIEW_DOC is None else numbers[numbers["文献番号"] == PREVIEW_DOC]
preview = None
for _, row in candidates.iterrows():
    path = Path(TEXT_DIR) / f"{row['Google Patents ID(推定)']}.json"
    if path.exists():
        preview = (row["文献番号"], json.loads(path.read_text(encoding="utf-8")))
        break

# LLM に実際に渡る文章(システム + ユーザー + 出力形式の指示)だけを表示する。生成はしない。
if preview:
    print(f"確認する特許: {preview[0]}\\n")
    print(render_prompt(backend, topic, preview[0], preview[1], MAX_CHARS))
else:
    print("全文 JSON がまだありません(手順2で本文も CSV の要約も得られた特許がありません)。プロンプトは表示しません。")'''

STEP2_RUN = """# LIMIT が None なら全件、数字ならその件数だけを対象にする。
targets = numbers if LIMIT is None else numbers.head(LIMIT)
# 取得・抽出を実行し、結果の表を受け取る。
result = run(targets, Path(HTML_DIR), DELAY, Path(TEXT_DIR), Path(CACHE_DIR))
# 結果を Excel に保存する。
result.to_excel(RESULT_XLSX, index=False)
print('->', RESULT_XLSX)
# 取得状況・抽出状況などの要点だけを表示する。
result[[c for c in ['文献番号', 'ID', '使用ID', '取得状況', '抽出状況', '請求項数'] if c in result]]"""

STEP3_RUN = """# EVAL_LIMIT が None なら全件、数字ならその件数だけを対象にする。
targets3 = numbers if EVAL_LIMIT is None else numbers.head(EVAL_LIMIT)
# 評価の前に、全文 JSON がある特許の数を確認する(1 件もなければ、原因と対処を表示して止まる)。
check_texts(targets3, TEXT_DIR, RESULTS_ROOT, run_dir)
# LLM で 1 件ずつ評価し、結果の表を受け取る。STREAM が True なら、生成の様子がリアルタイムで表示される。
evaluation = evaluate_table(backend, topic, targets3, TEXT_DIR, MAX_CHARS, COMPANY_ALIASES, stream=STREAM)
# 結果を Excel に保存する(文献番号をクリックで Google Patents が開く。列と順番は固定)。
save_evaluation_excel(evaluation, RESULT_EVAL_XLSX)
print('->', RESULT_EVAL_XLSX)
# 結果の表を画面に表示する(リンク列は Excel 側でだけ使うので除く)。
evaluation.drop(columns=["リンク"])"""

md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell


_n = [0]


def explain(title, work, inp, out):
    """各コードセルの直前に置く説明(作業・入力・出力)。"""
    _n[0] += 1
    return md(f"### セル{_n[0]}: {title}\n- **作業**: {work}\n- **入力**: {inp}\n- **出力**: {out}")


cells = [
    md("# 特許調査パイプライン（ステップ1〜3）\n"
       "1. 指定フォルダ内の J-PlatPat 検索結果（コピーしたテキスト txt、またはダウンロードした csv。どちらも複数可）を統合し、重複を除いた文献番号表を作る\n"
       "2. 文献番号から Google Patents（日本語ページ）の HTML を取得し、名称・要約・請求項・明細書を Excel に出力する（取得できない場合は、csv の要約で代用）\n"
       "3. ローカル LLM で、各特許が「調べたいこと」に関連するかを評価して表にする\n\n"
       "**使い方**: 上から順に実行。まず設定セルの値を変更し、手順2・3は `LIMIT` / `EVAL_LIMIT = 3` などで少数件を試してから全件にしてください。\n\n"
       "**各セルの説明は、そのセルの上にあります。** プログラム本体のセル（タイトルが「プログラム○」のもの）は、先頭にそのプログラムの作業の流れが書いてあります。\n\n"
       "注意: Google Patents の自動取得は利用規約上の制限を受け得ます。`DELAY` を空けて、必要な件数だけ実行してください。"),

    explain("ライブラリの準備",
            "必要な Python ライブラリ(表計算・Excel 出力・通信・HTML 解析)を入れる。入っていれば何もしない",
            "なし", "なし(ライブラリが使える状態になる)"),
    code("%pip install -q pandas openpyxl requests beautifulsoup4 lxml"),

    explain("設定（調べたいことはここに書く）",
            "フォルダ・出力先・件数などの設定と、手順3の「調べたいこと」、使う LLM を決める。各設定の上にその意味を書いてある",
            "あなたが書き換える値", "なし(以降のセルが、ここの値を使う)"),
    code(SETTINGS),

    md("## 調査フォルダの作成"),
    explain("プログラム0: 調査フォルダの作成と登録",
            "「トピック名_日時」のフォルダを作り、入力の txt と設定を登録する。同じ調査を続ける場合は、既存のフォルダを指定できる",
            "なし(関数を定義するだけ)", "なし(次のセルで使う関数 make_run_dir などができる)"),
    code(runs_src),
    explain("調査フォルダの作成",
            "設定のトピック名と現在の日時で調査フォルダを作り(同じ起動中に再実行した場合は、同じトピックの直前のフォルダを続けて使う)、入力の txt を input/ にコピーし、設定を run_settings.json に保存する。"
            "以降の出力は、すべてこのフォルダの中に入る(html/ text/ patent_numbers.xlsx patents_text.xlsx evaluation.xlsx)",
            "設定のトピック名・RUN_DIR・各設定、INPUT_DIR の txt / csv", "調査フォルダ、run_dir、各出力ファイルの場所(NUMBERS_XLSX など)"),
    code(RUN_CELL),
    md("## 手順1: 文献番号の一覧を作る"),
    explain("プログラム1: テキストの読み取り",
            "J-PlatPat の結果一覧（txt は 1 件ずつに区切り、csv は 1 行ずつ読み）、文献番号・出願番号・日付・名称・出願人・ステータス・FI（csv は要約も）に振り分ける。"
            "フォルダ内の複数ファイルをまとめ、文献番号で重複を除く。Google Patents の ID 候補も作る",
            "なし(関数を定義するだけ)", "なし(次のセルで使う関数 parse_text・build_list などができる)"),
    code(platpat),
    explain("手順1の実行: 一覧の作成",
            "設定したフォルダの全ファイル（INPUT_FORMAT で選んだ txt / csv）を読み、重複を除いた文献番号の一覧を作って Excel に保存する。csv の場合は、要約も一覧に入る",
            "設定の INPUT_DIR 内の txt / csv", "numbers(一覧)、report(報告)、調査フォルダ内の patent_numbers.xlsx"),
    code(STEP1_RUN),
    explain("確認: ファイル間で内容が違った行",
            "同じ文献番号でファイル間にステータス等の違いがあった行を表示する。新しいファイルの内容を採用済み",
            "report", "表(空なら該当なし)"),
    code("report['conflicts']"),
    explain("確認: 読み取れなかった行",
            "文献番号や日付の書式が想定と違い、読み取りに警告が出た行を表示する",
            "numbers", "表(空なら問題なし)"),
    code("numbers[numbers['警告'] != ''][['No.', '文献番号', '警告']]"),
    explain("確認: 同じ出願番号で別の文献番号の行",
            "同じ出願番号で文献番号が違う行(公開公報と登録公報など)を表示する。除外はしていないので、重複評価を避けたい場合の参考にする",
            "numbers", "表"),
    code("numbers[numbers['同一出願番号の別文献'] != ''][['文献番号', '出願番号', '同一出願番号の別文献']]"),

    md("## 手順2: Google Patents から本文を取得する"),
    explain("プログラム2: HTML の取得と本文の抽出",
            "文献番号から Google Patents の日本語ページの HTML を取得して保存し、名称・要約・請求項・明細書を取り出す。"
            "全文は切り詰めずに JSON でも保存する(原文と、全角を半角に揃えた版)",
            "なし(関数を定義するだけ)", "なし(次のセルで使う関数 run などができる)"),
    code(fetch_src),
    explain("手順2の実行: 取得と抽出",
            "一覧の先頭から LIMIT 件について、HTML を取得し本文を抽出して Excel に保存する。取得済みの HTML は再利用する。404 などで取得できなかった場合、csv の要約があれば、それだけを本文として使う（「本文の出所」列に「CSVの要約のみ」と出る。評価の理由にも「【要約のみで判定】」と付く）",
            "numbers、設定の LIMIT・DELAY", "result(表)、調査フォルダ内の patents_text.xlsx、html/、text/(共有キャッシュにも HTML を保存)"),
    code(STEP2_RUN),
    explain("確認: 取得・抽出に失敗した行",
            "取得状況が 200 / cache 以外、または抽出状況が OK 以外の行を表示する。要約で代用した行もここに出る",
            "result", "表(空なら全件成功)"),
    code("result[(result['取得状況'].isin(['200', 'cache']) == False) | (result.get('抽出状況', 'OK') != 'OK')]"),

    md("## 手順3: LLM による関連性の評価"),
    explain("プログラム3: 関連性の評価",
            "調べたいことの関連語の周辺を本文から抜粋し、判定基準と一緒に LLM へのプロンプトを作って判定させる。"
            "判定は JSON の形式に制約され、「根拠の引用」が原文に実在するかも自動で確認する",
            "なし(関数を定義するだけ)", "なし(次の 2 つのセルで使う関数ができる)"),
    code(evaluate_src),
    explain("LLM の準備とプロンプトの確認",
            "設定の BACKEND・OLLAMA_FORMAT に応じて LLM に問い合わせる準備をし、調べたいことをまとめ、実際に LLM に渡る文章（システムプロンプトとユーザープロンプト。出力形式の指示を含む）だけを 1 件分表示する。生成はしないので、次のセルで評価を始める前に、渡る内容を確認できる。確認する特許は PREVIEW_DOC で選ぶ。"
            "ollama は Ollama の起動と `ollama pull qwen3:14b` 済みであること。"
            "guidance は `pip install guidance transformers torch accelerate` が必要で、モデルは初回に Hugging Face から取得される",
            "設定の BACKEND・TOPIC_*、調査フォルダ内 text/ の全文 JSON", "backend、topic、プロンプトの見本(画面表示)"),
    code(BACKEND_CELL),
    explain("手順3の実行: 評価",
            "まず、評価する特許のうち全文 JSON がある件数を確認する(1 件もなければ、原因と対処を表示して止まる)。そのうえで、一覧の先頭から EVAL_LIMIT 件を LLM で評価する。設定の STREAM が True なら、LLM が生成している様子を 1 語ずつリアルタイムで表示する（プロンプトは表示しない。確認は直前のセル）。結果は、関連度の高い順の Excel にする。列は、文献番号(Google Patents へのリンク。csv の要約で代用した行だけ J-PlatPat へのリンク)、判定、関連度、関連語ヒット数、理由、引用の検証、根拠の引用、発明の名称、出願人・権利者、出願企業、ステータス、発明内容概要",
            "numbers、調査フォルダ内 text/ の全文 JSON、backend、topic", "evaluation(表)、調査フォルダ内の evaluation.xlsx"),
    code(STEP3_RUN),
    explain("文字化けの診断（必要なときだけ実行）",
            "返答が文字化けする場合に、同じ質問を Ollama の 3 つの方式（通常 / JSON モード / 構造化出力）で送り、どの方式で文字化けが出るかを表示する。"
            "構造化出力でだけ文字化けする場合は、設定の OLLAMA_FORMAT を \"none\" にする。全方式で出る場合は、Ollama・モデル側の問題の可能性がある",
            "設定の OLLAMA_MODEL・OLLAMA_NUM_CTX（Ollama が起動していること）", "各方式の返答と、文字化けの有無（画面表示のみ）"),
    code("# 3 つの方式で同じ質問を送り、返答の文字化けの有無を表示する(BACKEND が ollama の場合のみ)。\n"
         "diagnose_ollama(OLLAMA_MODEL, num_ctx=OLLAMA_NUM_CTX)"),
]
nb = nbf.v4.new_notebook(cells=cells)
nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
nbf.write(nb, root / "notebooks/patent_pipeline.ipynb")
print("written")
