import json
from datetime import datetime

import pytest

from patent_search.runs import make_run_dir, register_inputs, safe_name, save_run_settings

NOW = datetime(2026, 10, 4, 15, 30, 5)


def test_safe_name():
    # Windows で使えない文字( / : " )は除き、空白は _ にする
    assert safe_name('SHAPE法（RNA構造/化学: "プロービング"）') == "SHAPE法（RNA構造化学_プロービング）"
    assert "/" not in safe_name("a/b\\c:d*e?f") and safe_name("   ") == "調査"
    assert len(safe_name("あ" * 100)) == 40


def test_make_run_dir_name_and_subdirs(tmp_path):
    d = make_run_dir(tmp_path, "TOTAL-RNA-seq", now=NOW)
    assert d.name == "TOTAL-RNA-seq_20261004_153005"
    assert all((d / s).is_dir() for s in ("html", "text", "input"))
    again = make_run_dir(tmp_path, "TOTAL-RNA-seq", now=NOW)  # 同じ秒でも別フォルダ
    assert again != d and again.name.endswith("_2")


def test_resume_existing_run_dir(tmp_path):
    d = make_run_dir(tmp_path, "T", now=NOW)
    assert make_run_dir(tmp_path, "T", run_dir=d.name) == d  # フォルダ名だけでも指定できる
    assert make_run_dir(tmp_path, "T", run_dir=str(d)) == d
    with pytest.raises(FileNotFoundError):
        make_run_dir(tmp_path, "T", run_dir="なし")


def test_register_inputs_and_settings(tmp_path):
    src = tmp_path / "in"
    src.mkdir()
    (src / "a.txt").write_text("x", encoding="utf-8")
    d = make_run_dir(tmp_path / "res", "T", now=NOW)
    assert register_inputs(d, src) == ["a.txt"] and (d / "input" / "a.txt").exists()
    data = json.loads(save_run_settings(d, {"トピック名": "T", "件数": None}).read_text(encoding="utf-8"))
    assert data["トピック名"] == "T" and "作成日時" in data
