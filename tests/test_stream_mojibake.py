import json

import pandas as pd
import pytest

from patent_search import evaluate
from patent_search.evaluate import (SCHEMA, Topic, evaluate_one, evaluate_table, extract_json, guidance_backend,
                                    looks_garbled, ollama_backend, repair_mojibake, validate_output)

TEXT = "全RNA（トータルRNA）は、rRNAを除去して読む手法である。ＲＮＡ，ｍＲＮＡ"


def garble(text, enc):
    return text.encode("utf-8").decode(enc, errors="replace")


@pytest.mark.parametrize("enc", ["latin-1", "cp1252"])
def test_repair_mojibake_roundtrip(enc):
    bad = garble(TEXT, enc)
    assert looks_garbled(bad) and bad != TEXT
    # latin-1 は C1 制御文字(U+0080-9F)がそのまま入る。cp1252 は ‚ƒ„… などに置き換わる(未定義の 5 文字は U+FFFD になり戻せない)
    fixed = repair_mojibake(bad)
    if enc == "latin-1":
        assert fixed == TEXT
    else:
        assert not looks_garbled(fixed) or "�" in bad


def test_repair_mojibake_cp1252_variant_used_by_windows():
    # Windows の cp1252 相当(未定義バイトは C1 制御文字のまま)で読まれた場合
    raw = TEXT.encode("utf-8")
    bad = "".join(bytes([b]).decode("cp1252", errors="ignore") or chr(b) for b in raw)
    assert looks_garbled(bad)
    assert repair_mojibake(bad) == TEXT


def test_repair_leaves_normal_text_and_mixed_text():
    assert repair_mojibake(TEXT) == TEXT and not looks_garbled(TEXT)
    assert not looks_garbled("µm と ±5° と café と ö")  # 正しい欧文は誤検出しない
    mixed = "前半は正常。" + garble("あいう", "latin-1") + " 後半も正常。"
    assert repair_mojibake(mixed) == "前半は正常。あいう 後半も正常。"  # 文字化けした部分だけ直す


def test_bom_mojibake_detected():
    assert looks_garbled("ï»¿ï»¿")
    assert "﻿" not in validate_output({"score": 1, "reason": "﻿あ"})["reason"]


def test_extract_json_and_validate():
    assert json.loads(extract_json('説明です。```json\n{"score": 2}\n``` 以上')) == {"score": 2}
    with pytest.raises(ValueError):
        extract_json("JSON はありません")
    v = validate_output({"score": "2", "reason": "あ" * 500, "summary": "s", "evidence": "引用1"})
    assert v["score"] == 2 and v["judgement"] == "関連あり" and len(v["reason"]) == 300 and v["evidence"] == ["引用1"]
    for bad in ({}, {"score": 7}, {"score": "x"}, [1]):
        with pytest.raises(ValueError):
            validate_output(bad)


class FakeResponse:
    def __init__(self, chunks):
        self._chunks = chunks
        self.headers = {"Content-Type": "application/x-ndjson"}

    def raise_for_status(self):
        pass

    def iter_lines(self):
        for c in self._chunks:
            yield json.dumps({"message": {"content": c}}, ensure_ascii=False).encode("utf-8")  # bytes で返す

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


GOOD = {"score": 2, "judgement": "関連あり", "reason": "実施例で使用", "summary": "全RNAを読む方法", "evidence": []}


def test_ollama_backend_streams_utf8_and_retries(monkeypatch):
    calls = []

    def fake_post(url, json=None, stream=None, timeout=None):
        calls.append(json)
        if len(calls) == 1:
            return FakeResponse(["JSONではない", "文章です"])  # 1 回目は読めない → やり直し
        text = __import__("json").dumps(GOOD, ensure_ascii=False)
        return FakeResponse([text[:10], text[10:]])

    import requests

    monkeypatch.setattr(requests, "post", fake_post)
    shown = []
    out = ollama_backend(mode="none")("sys", "user", SCHEMA, on_token=shown.append)
    assert json.loads(out)["score"] == 2 and len(calls) == 2
    assert calls[0]["stream"] is True and "format" not in calls[0]  # none: 構造化出力を使わない
    assert "# 出力形式" in calls[0]["messages"][1]["content"]
    assert "やり直します" in "".join(shown) and "全RNA" in "".join(shown)  # 生成が 1 語ずつ渡る・日本語が正しい


def test_ollama_backend_modes_send_format(monkeypatch):
    import requests

    seen = {}
    monkeypatch.setattr(requests, "post", lambda url, json=None, **k: seen.setdefault("b", json) and FakeResponse(
        [__import__("json").dumps(GOOD, ensure_ascii=False)]))
    ollama_backend(mode="schema")("s", "u", SCHEMA)
    assert seen["b"]["format"] == SCHEMA and "# 出力形式" not in seen["b"]["messages"][1]["content"]
    seen.clear()
    ollama_backend(mode="json")("s", "u", SCHEMA)
    assert seen["b"]["format"] == "json"


def test_ollama_backend_gives_up_after_retries(monkeypatch):
    import requests

    n = []
    monkeypatch.setattr(requests, "post", lambda *a, **k: n.append(1) or FakeResponse(["だめ"]))
    with pytest.raises(ValueError, match="JSON を得られませんでした"):
        ollama_backend(mode="none", retries=2)("s", "u", SCHEMA)
    assert len(n) == 3  # 最初の 1 回 + やり直し 2 回


REC = {"title_nfkc": "t", "abstract_nfkc": "全RNAを使う", "claims_nfkc": "c", "description_nfkc": "全RNA を使う実施例"}
TOPIC = Topic("TOTAL-RNA-seq", "全RNA", ["全RNA"])


def test_evaluate_one_repairs_garbled_llm_output():
    bad = {"score": 2, "judgement": "関連あり", "reason": garble("実施例で使用（確認）", "latin-1"),
           "summary": "正常な概要", "evidence": [garble("全RNA を使う実施例", "latin-1")]}
    out = evaluate_one(lambda *a, **k: json.dumps(bad, ensure_ascii=False), TOPIC, "特開X", REC)
    assert out["reason"] == "【文字化けを補正】実施例で使用（確認）"
    assert out["evidence"] == ["全RNA を使う実施例"] and out["evidence_check"] == "全て原文に存在"


def test_evaluate_one_flags_unrepairable_garble():
    # UTF-8 として読み直せない(途中で切れた)文字化けは、直さずに「疑い」と表示する
    bad = {"score": 1, "reason": "ãã¡ãã¡", "summary": "", "evidence": []}
    out = evaluate_one(lambda *a, **k: json.dumps(bad, ensure_ascii=False), TOPIC, "特開X", REC)
    assert "文字化けの疑い" in out["evidence_check"] and "【文字化けを補正】" not in out["reason"]
    # BOM だけに化けている場合は、直して(ゼロ幅の文字を除いて)空になる
    bom = {"score": 1, "reason": "ï»¿ï»¿結果", "summary": "", "evidence": []}
    assert evaluate_one(lambda *a, **k: json.dumps(bom, ensure_ascii=False), TOPIC, "特開X", REC)["reason"].endswith("結果")


def test_evaluate_table_streams_to_screen(capsys, tmp_path):
    (tmp_path / "JP1A.json").write_text(json.dumps(REC), encoding="utf-8")
    nums = pd.DataFrame([{"文献番号": "特開1", "Google Patents ID(推定)": "JP1A", "発明の名称": "名称A"}])

    def backend(system, user, schema, on_token=None):
        text = json.dumps(GOOD, ensure_ascii=False)
        for ch in (text[:5], text[5:]):
            on_token(ch)  # 生成の途中経過
        return text

    df = evaluate_table(backend, TOPIC, nums, tmp_path, stream=True)
    screen = capsys.readouterr().out
    assert "━━ 特開1  名称A" in screen and '"score": 2' in screen and "→ 特開1 関連度=2 関連あり" in screen
    assert df.loc[0, "関連度"] == 2
    # stream=False なら生成の途中経過は出さない
    evaluate_table(lambda s, u, sc: json.dumps(GOOD, ensure_ascii=False), TOPIC, nums, tmp_path)
    assert '"score"' not in capsys.readouterr().out


def test_guidance_backend_streams_with_mock_and_falls_back():
    from guidance import models

    shown = []
    out = guidance_backend(models.Mock())("sys", "user", SCHEMA, on_token=shown.append)
    assert json.loads(out)["score"] in (0, 1, 2, 3)
    assert "".join(shown).startswith('{"score"')  # 生成された JSON が画面用に流れる
    assert json.loads(guidance_backend(models.Mock())("sys", "user", SCHEMA))["judgement"]  # on_token なしでも動く


def test_diagnose_ollama_reports_garble(monkeypatch, capsys):
    import requests

    class R:
        headers = {"Content-Type": "application/json; charset=utf-8"}

        def __init__(self, text):
            self.content = json.dumps({"message": {"content": text}}, ensure_ascii=False).encode("utf-8")

        def json(self):
            return {"version": "0.9.0"}

    texts = iter(["全RNAは（正常）です", garble("全RNAは（文字化け）です", "latin-1"), "全RNAは（正常）です"])
    monkeypatch.setattr(requests, "get", lambda *a, **k: R("x"))
    monkeypatch.setattr(requests, "post", lambda *a, **k: R(next(texts)))
    evaluate.diagnose_ollama()
    screen = capsys.readouterr().out
    assert screen.count("文字化けの疑い: なし") == 2 and screen.count("文字化けの疑い: あり") == 1
    assert "補正後: 全RNAは（文字化け）です" in screen


def test_render_prompt_includes_system_user_and_backend_note():
    from patent_search.evaluate import render_prompt

    text = render_prompt(ollama_backend(mode="none"), TOPIC, "特開1", REC)
    i, j = text.index("【システムプロンプト】"), text.index("【ユーザープロンプト】")
    assert i < j and "あなたは特許調査の専門家" in text and "# 調査テーマ\nTOTAL-RNA-seq" in text
    assert "# 出力形式" in text and text.rstrip().endswith('"evidence": ["本文からの引用"]}')  # 渡る文章の末尾まで
    # 構造化出力(schema)では、出力形式の指示は足されない。バックエンドの指定が無ければ(guidance など)足さない
    assert "# 出力形式" not in render_prompt(ollama_backend(mode="schema"), TOPIC, "特開1", REC)
    assert "# 出力形式" not in render_prompt(lambda *a, **k: "", TOPIC, "特開1", REC)


def test_evaluate_table_does_not_print_prompt(capsys, tmp_path, monkeypatch):
    import requests

    (tmp_path / "JP1A.json").write_text(json.dumps(REC), encoding="utf-8")
    nums = pd.DataFrame([{"文献番号": "特開1", "Google Patents ID(推定)": "JP1A", "発明の名称": "名称A"}])
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse([json.dumps(GOOD, ensure_ascii=False)]))
    evaluate_table(ollama_backend(mode="none"), TOPIC, nums, tmp_path, stream=True)
    screen = capsys.readouterr().out
    assert "【ユーザープロンプト】" not in screen and "# 調査テーマ" not in screen  # プロンプトは出さない
    assert "━━ 特開1  名称A" in screen and '"score": 2' in screen  # 生成の様子だけ出る


