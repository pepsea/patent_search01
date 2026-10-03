# Patent Search

Google Patents の表示画面をスクレイピングせず、Google が公開している
`patents-public-data.patents.publications` を BigQuery で検索するための Python CLI です。
再現可能な SQL、検索条件、取得日時を結果と一緒に保存するため、先行技術調査の
**検索ログ**として使えます（法的な網羅性・有効性判断そのものを保証するものではありません）。

## セットアップ

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
gcloud auth application-default login
```

BigQuery API を有効化した課金プロジェクト ID を指定してください。公開データセットを読む
クエリでも、ジョブを実行するプロジェクトは必要です。

## まずは費用を確認する（実行しない）

`--dry-run` が既定値です。処理予定バイト数だけを表示し、検索結果ファイルを作りません。

```bash
python -m patent_search --project YOUR_PROJECT --query "solid state battery" --country JP --from 2015-01-01
```

## 検索・CSV 出力

```bash
python -m patent_search --project YOUR_PROJECT \
  --query "solid state battery" \
  --country JP --country US \
  --cpc H01M --from 2015-01-01 --to 2025-12-31 \
  --max-results 500 --max-bytes 2000000000 \
  --output results/battery.csv
```

検索語は title / abstract / claims の英語テキストを対象とします。`--cpc`（例: `H01M` は
その配下を含む）、`--assignee`、`--inventor`、出願日、公開国を組み合わせ、同義語・表記ゆれ・IPC/CPC を
変えた複数回の検索を推奨します。検索結果には Google Patents の直接リンク、優先日、
出願人・発明者、CPC を含めます。各 CSV と同じ場所に `.metadata.json` を保存します。

## BigQuery は無料？

完全に無制限ではありません。2026-10-03 時点で on-demand 分析クエリは毎月最初の
**1 TiB**、保存は毎月最初の **10 GiB** が無料です。超過分の on-demand クエリは
データ処理量に応じて課金されます。BigQuery Sandbox はクレジットカードなしで試せますが、
同じ 1 TiB/月のクエリ上限と 10 GiB の生涯ストレージ上限があります。
公式料金ページ: <https://cloud.google.com/bigquery/pricing>、Sandbox:
<https://cloud.google.com/bigquery/docs/sandbox>。

この CLI は (1) 既定の dry run、(2) `--max-bytes` による BigQuery の上限、(3) 必要列だけを
選択する SQL で、意図しないスキャンを抑えます。実行前に必ず dry run のバイト数を確認し、
Cloud Billing の予算・アラートも設定してください。
