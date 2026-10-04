"""特許本文と「調べたいこと」の関連性を、ローカル LLM で評価する（ステップ3）。

- 判定結果は JSON スキーマで制約する（Ollama: format 指定 / Hugging Face: guidance の json 文法）。
  どちらのバックエンドでも同じプロンプト・同じスキーマなので、サーバー移植時はバックエンドだけ差し替える。
- LLM が出した「根拠の引用」が本当に原文にあるかを機械的に確認し、結果に付ける（幻覚の検出）。
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable

SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "enum": [0, 1, 2, 3]},
        "judgement": {"type": "string", "enum": ["直接関連", "関連あり", "わずかに関連", "無関係"]},
        "reason": {"type": "string", "maxLength": 300},
        "evidence": {"type": "array", "items": {"type": "string", "maxLength": 200}, "maxItems": 3},
    },
    "required": ["score", "judgement", "reason", "evidence"],
    "additionalProperties": False,
}

SYSTEM = "あなたは特許調査の専門家です。与えられた特許の本文が、指定された調査テーマに関連するかを、根拠を示して厳密に判定します。"

USER_TEMPLATE = """# 調査テーマ
{name}

## テーマの定義
{definition}

## 関連語（同義語・日英表記）
{keywords}

## 含める条件（関連とみなす）
{include}

## 除外する条件（関連とみなさない）
{exclude}

# 判定基準
- 3 (直接関連): 特許の中心的な内容（請求項・要約）が、このテーマの手法・対象そのものである
- 2 (関連あり): テーマの手法・対象を、明細書や実施例で実際に使用・言及している（請求項の中心ではない）
- 1 (わずかに関連): 関連語が出るが、一般的な背景説明や列挙の一部にとどまる
- 0 (無関係): 関連しない

# 対象特許
文献番号: {doc_no}
名称: {title}

## 要約
{abstract}

## 請求項
{claims}

## 明細書（関連語の周辺の抜粋 / 先頭部分）
{description}

# 出力
JSON のみを出力する。evidence には、上の本文からそのまま抜き出した短い引用（最大3件、各200字以内、改変禁止）を入れる。
根拠が本文にない場合は evidence を空配列にし、score は 0 か 1 にする。"""


@dataclass
class Topic:
    name: str
    definition: str
    keywords: list[str] = field(default_factory=list)
    include: str = ""
    exclude: str = ""


def nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s)


def _keyword_patterns(keywords: list[str]) -> list[re.Pattern]:
    """通常の語は大文字小文字を区別しない。SHAPE・NAI・DMS のような大文字だけの短い略語は、
    shape(形状)・naive・DGSHAPE 等への誤一致を避けるため、大文字小文字を区別し前後に英数字がある場合は除外する。"""
    ci, strict = [], []
    for k in map(nfkc, keywords):
        if re.fullmatch(r"[A-Z0-9]{2,6}", k):
            strict.append(r"(?<![A-Za-z0-9])" + re.escape(k) + r"(?![A-Za-z0-9])")
        else:
            ci.append(re.escape(k))
    pats = []
    if ci:
        pats.append(re.compile("|".join(ci), re.IGNORECASE))
    if strict:
        pats.append(re.compile("|".join(strict)))
    return pats


def keyword_snippets(text: str, keywords: list[str], width: int = 150, max_snippets: int = 8) -> tuple[list[str], int]:
    """関連語の前後 width 文字を抜粋する(重なる範囲は結合)。(抜粋, 全ヒット数) を返す。"""
    if not keywords:
        return [], 0
    hits = sorted(m.span() for pat in _keyword_patterns(keywords) for m in pat.finditer(text))
    spans: list[list[int]] = []
    for a, b in hits:
        a, b = max(0, a - width), min(len(text), b + width)
        if spans and a <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], b)
        else:
            spans.append([a, b])
    return [text[a:b].replace("\n", " ") for a, b in spans[:max_snippets]], len(hits)


def build_prompt(topic: Topic, doc_no: str, rec: dict, max_chars: int = 6000) -> tuple[str, int]:
    """rec は全文JSON(*_nfkc キーを使う)。max_chars で本文の長さを抑える。(プロンプト, 関連語ヒット数)"""
    desc = rec["description_nfkc"]
    snippets, hits = keyword_snippets(desc, topic.keywords)
    body = "\n---\n".join(snippets) if snippets else desc[:1500]
    claims = rec["claims_nfkc"]
    prompt = USER_TEMPLATE.format(
        name=topic.name, definition=topic.definition.strip(),
        keywords="、".join(topic.keywords) or "(なし)", include=topic.include.strip() or "(指定なし)",
        exclude=topic.exclude.strip() or "(指定なし)", doc_no=doc_no, title=rec["title_nfkc"],
        abstract=rec["abstract_nfkc"][:1500], claims=claims[: max_chars // 2], description=body[: max_chars // 2],
    )
    return prompt, hits


# ---- バックエンド: (system, user, schema) -> JSON 文字列 -------------------------------

def ollama_backend(model: str = "qwen3:14b", host: str = "http://localhost:11434", num_ctx: int = 8192) -> Callable:
    import requests

    def run(system: str, user: str, schema: dict) -> str:
        r = requests.post(f"{host}/api/chat", timeout=600, json={
            "model": model, "stream": False, "think": False, "format": schema,
            "options": {"temperature": 0, "num_ctx": num_ctx},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        })
        r.raise_for_status()
        return r.json()["message"]["content"]

    return run


def guidance_backend(lm) -> Callable:
    """lm: guidance のモデル。例: guidance.models.Transformers("Qwen/Qwen3-14B", device_map="auto")。"""
    from guidance import assistant, system as system_role, user as user_role
    from guidance import json as gjson

    def run(system: str, user: str, schema: dict) -> str:
        m = lm
        with system_role():
            m += system
        with user_role():
            m += user
        with assistant():
            m += gjson(name="out", schema=schema)
        return m["out"]

    return run


# ---- 評価 ----------------------------------------------------------------------------

def check_evidence(evidence: list[str], source: str) -> str:
    """引用が原文(NFKC・空白除去)に含まれるかを確認する。"""
    norm = lambda s: re.sub(r"\s+", "", nfkc(s))
    if not evidence:
        return "引用なし"
    src = norm(source)
    ok = sum(norm(e) in src for e in evidence)
    return "全て原文に存在" if ok == len(evidence) else f"原文に無い引用あり({len(evidence) - ok}/{len(evidence)})"


def evaluate_one(backend: Callable, topic: Topic, doc_no: str, rec: dict, max_chars: int = 6000) -> dict:
    prompt, hits = build_prompt(topic, doc_no, rec, max_chars)
    try:
        out = json.loads(backend(SYSTEM, prompt, SCHEMA))
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        return {"score": None, "judgement": "判定失敗", "reason": f"{type(e).__name__}: {e}", "evidence": [],
                "evidence_check": "", "keyword_hits": hits}
    source = rec["abstract_nfkc"] + rec["claims_nfkc"] + rec["description_nfkc"]
    out["evidence_check"] = check_evidence(out.get("evidence", []), source)
    out["keyword_hits"] = hits
    return out


def evaluate_table(backend: Callable, topic: Topic, numbers, text_dir, max_chars: int = 6000):
    """文献番号表(numbers: DataFrame)の各行を、全文JSON(text_dir/{ID}.json)で評価し、結果の表を返す。"""
    from pathlib import Path

    import pandas as pd

    rows = []
    for _, r in numbers.iterrows():
        pid = r.get("Google Patents ID(推定)")
        path = Path(text_dir) / f"{pid}.json"
        base = {"文献番号": r["文献番号"], "発明の名称": r.get("発明の名称"), "出願人/権利者": r.get("出願人/権利者"),
                "ステータス": r.get("ステータス"), "Google Patents URL": r.get("Google Patents URL(推定)")}
        if not path.exists():
            rows.append({**base, "判定": "本文なし(未取得)"})
            continue
        rec = json.loads(path.read_text(encoding="utf-8"))
        try:
            o = evaluate_one(backend, topic, r["文献番号"], rec, max_chars)
        except Exception as e:  # 接続断など。1件の失敗で全体を止めない
            o = {"score": None, "judgement": "判定失敗", "reason": f"{type(e).__name__}: {e}", "evidence": [],
                 "evidence_check": "", "keyword_hits": None}
        rows.append({**base, "関連度(0-3)": o["score"], "判定": o["judgement"], "理由": o["reason"],
                     "根拠の引用": " / ".join(o["evidence"]), "引用の検証": o["evidence_check"],
                     "関連語ヒット数": o["keyword_hits"]})
        print(r["文献番号"], o["score"], o["judgement"], flush=True)
    df = pd.DataFrame(rows)
    if "関連度(0-3)" in df:
        df = df.sort_values("関連度(0-3)", ascending=False, na_position="last", kind="stable")
    return df.reset_index(drop=True)
