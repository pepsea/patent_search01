import json

from patent_search.evaluate import (SCHEMA, Topic, build_prompt, check_evidence, evaluate_one,
                                    guidance_backend, keyword_snippets)

REC = {
    "title_nfkc": "RNA三次構造予測", "abstract_nfkc": "要約",
    "claims_nfkc": "【請求項1】total RNA-seqを用いる方法",
    "description_nfkc": "背景。" * 100 + "rRNA depletion を行った total RNA sequencing により解析する。" + "末尾。" * 100,
}
TOPIC = Topic("TOTAL-RNA-seq", "全RNAを対象にしたシーケンス", ["total RNA", "rRNA depletion", "全RNA"])


def test_snippets_merge_and_count():
    sn, hits = keyword_snippets(REC["description_nfkc"], TOPIC.keywords)
    assert hits == 2 and len(sn) == 1  # 近接するヒットは1つの抜粋に結合
    assert keyword_snippets("なし", []) == ([], 0)


def test_prompt_contains_topic_and_snippet():
    p, hits = build_prompt(TOPIC, "特開X", REC)
    assert "TOTAL-RNA-seq" in p and "rRNA depletion" in p and "特開X" in p and hits == 2


def test_evidence_check():
    src = "total RNA sequencing により解析"
    assert check_evidence(["total RNA sequencing"], src) == "全て原文に存在"
    assert "原文に無い" in check_evidence(["作り話"], src)
    assert check_evidence([], src) == "引用なし"


def test_evaluate_one_with_fake_backend():
    fake = lambda s, u, schema: json.dumps({"score": 3, "judgement": "直接関連", "reason": "r",
                                             "evidence": ["total RNA-seqを用いる方法"]})
    r = evaluate_one(fake, TOPIC, "特開X", REC)
    assert r["score"] == 3 and r["evidence_check"] == "全て原文に存在" and r["keyword_hits"] == 2


def test_evaluate_one_handles_bad_json():
    assert evaluate_one(lambda *a: "not json", TOPIC, "特開X", REC)["judgement"] == "判定失敗"


def test_guidance_backend_returns_schema_valid_json():
    # 実モデルの代わりに guidance の Mock で、文法制約つき生成の経路だけ確認する
    from guidance import models

    out = json.loads(guidance_backend(models.Mock())("sys", "user", SCHEMA))
    assert out["score"] in (0, 1, 2, 3) and out["judgement"] in SCHEMA["properties"]["judgement"]["enum"]


def test_evaluate_table(tmp_path):
    import pandas as pd

    from patent_search.evaluate import evaluate_table

    (tmp_path / "JP1A.json").write_text(json.dumps(REC), encoding="utf-8")
    nums = pd.DataFrame([
        {"文献番号": "特開1", "Google Patents ID(推定)": "JP1A", "発明の名称": "a"},
        {"文献番号": "特開2", "Google Patents ID(推定)": "JP2A", "発明の名称": "b"},
    ])
    fake = lambda s, u, schema: json.dumps({"score": 2, "judgement": "関連あり", "reason": "r", "evidence": []})
    df = evaluate_table(fake, TOPIC, nums, tmp_path)
    assert df.loc[0, "文献番号"] == "特開1" and df.loc[0, "関連度(0-3)"] == 2
    assert df.loc[1, "判定"] == "本文なし(未取得)"


def test_short_acronym_is_case_sensitive_and_bounded():
    text = "DGSHAPE社の shaped 形状。RNAをSHAPE-MaPで解析し、SHAPE試薬NAIを使う。naive な方法。"
    _, hits = keyword_snippets(text, ["SHAPE", "NAI"])
    assert hits == 3  # SHAPE-MaP の SHAPE、SHAPE試薬、NAI。DGSHAPE / shaped / naive は除外
    assert keyword_snippets("Total RNA-seq と total rna", ["total RNA"])[1] == 2  # 通常語は大小無視
