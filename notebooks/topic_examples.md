# 「調べたいこと」の書き方の手本

ノートブック上部の設定セルに貼り付けて使います。書き方の要点:
- **定義**は、手法の中身（何を、どう処理し、何を読むか）を書く。名前だけでは LLM が誤解する。
- **関連語**は、同義語・日英表記・試薬名・派生手法名を網羅する。2〜6字の大文字だけの略語（SHAPE, NAI, DMS など）は、
  大文字小文字を区別し、前後に英数字がある場合は除外して探す（`shape`＝形状、`DGSHAPE` 等への誤一致を避けるため）。
- **含める／除外する条件**は、判断が分かれる境界を決めて文章で書く。ここが判定の品質を最も左右する。

## 例1: TOTAL-RNA-seq

```python
TOPIC_NAME = "TOTAL-RNA-seq"
TOPIC_DEFINITION = """
TOTAL-RNA-seq（全RNAシーケンシング）とは、poly(A)選択でmRNAだけを濃縮するのではなく、
rRNA除去（rRNA depletion / ribo-depletion）などによって、mRNAに加えてlncRNA・非ポリA RNA・
前駆体RNAなどを含む全RNAを対象にライブラリを作製し、次世代シーケンサーで読み取る手法をいう。
"""
TOPIC_KEYWORDS = ["total RNA-seq", "total RNA sequencing", "total RNA", "whole transcriptome sequencing",
                  "rRNA depletion", "ribo-depletion", "Ribo-Zero", "全RNA", "トータルRNA", "rRNA除去"]
```

## 例2: SHAPE 法

```python
TOPIC_NAME = "SHAPE法（RNA構造の化学プロービング）"
TOPIC_DEFINITION = """
SHAPE（Selective 2'-Hydroxyl Acylation analyzed by Primer Extension）法とは、RNAの2'-水酸基を
アシル化する試薬（NAI、1M7、NMIA、2A3 など）でRNAを処理し、構造が柔軟な（一本鎖の）ヌクレオチドほど
修飾されやすいことを利用して、RNAの二次・三次構造を1塩基単位で推定する手法をいう。
修飾部位は、逆転写の停止（プライマー伸長）または変異として取り込まれる変異プロファイリング
（SHAPE-MaP）、あるいは次世代シーケンサーでの読み取り（SHAPE-seq、icSHAPE など）で検出する。
"""
TOPIC_KEYWORDS = [
    "SHAPE-MaP", "SHAPE-seq", "icSHAPE", "SHAPE", "selective 2'-hydroxyl acylation",
    "2'-hydroxyl acylation", "primer extension", "mutational profiling", "chemical probing", "chemical mapping",
    "NAI", "1M7", "NMIA", "2A3", "DMS",
    "2'-ヒドロキシルアシル化", "2'-水酸基", "化学プロービング", "化学マッピング", "変異プロファイリング", "RNA構造解析",
]
TOPIC_INCLUDE = """
SHAPE法またはSHAPE-MaP・SHAPE-seq・icSHAPEなどの派生手法でRNAの構造情報を取得する方法・試薬・解析ソフト。
SHAPEで得た反応性データを、RNAの構造予測や機械学習の入力に使う特許も含める。
"""
TOPIC_EXCLUDE = """
「shape」を「形状」の意味で使うもの（機械部品、車両部材など）。
RNAの構造に触れず、化学修飾にも関係しないもの。
DMS単独のプロービングは、SHAPEと併用している場合のみ関連とみなす。
"""
```

注意: DMS（硫酸ジメチル）単独の化学プロービングや、SHAPE以外の構造解析（クライオ電顕、X線結晶構造解析など）を
関連とみなすかは、調査の目的次第。上の例は「SHAPE法そのもの」に絞った場合の設定。
