"""プログラム0: 調査ごとの結果フォルダを作り、その中にデータを登録する。

作業の流れ:
 1. make_run_dir     : 「トピック名_日時」のフォルダ(中に html/ text/ input/)を作る。既存のフォルダを指定すれば続きから使う
 2. register_inputs  : 入力の txt を、調査フォルダの input/ にコピーして残す
 3. save_run_settings: 調べたいこと・LLM・件数などの設定を、調査フォルダの run_settings.json に保存する
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path


# 作業: トピック名を、フォルダ名に使える文字だけにする(Windows で使えない文字を除き、空白は _ にする)。
def safe_name(text: str, max_len: int = 40) -> str:
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", text or "")
    name = re.sub(r"\s+", "_", name.strip()).strip("._")
    return (name[:max_len].rstrip("._") or "調査")


# 作業: 調査フォルダを用意する。run_dir が None なら「トピック名_日時」を新規作成し、
# フォルダ名(または場所)が指定されていれば、その既存フォルダを続けて使う。
def make_run_dir(root: str | Path, topic_name: str, run_dir: str | Path | None = None,
                 now: datetime | None = None) -> Path:
    root = Path(root)
    if run_dir:
        found = [p for p in (Path(run_dir), root / run_dir) if p.is_dir()]
        if not found:
            raise FileNotFoundError(f"調査フォルダが見つかりません: {run_dir}")
        path = found[0]
    else:
        stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
        path = root / f"{safe_name(topic_name)}_{stamp}"
        n = 2
        while path.exists():  # 同じ秒に 2 回作った場合の重複を避ける
            path = root / f"{safe_name(topic_name)}_{stamp}_{n}"
            n += 1
    for sub in ("html", "text", "input"):
        (path / sub).mkdir(parents=True, exist_ok=True)
    return path


# 作業: 入力の txt を調査フォルダの input/ にコピーする。どの入力でその結果になったかを残すため。
def register_inputs(run_dir: Path, input_dir: str | Path, pattern: str = "*.txt") -> list[str]:
    copied = []
    for f in sorted(Path(input_dir).glob(pattern)):
        shutil.copy2(f, Path(run_dir) / "input" / f.name)
        copied.append(f.name)
    return copied


# 作業: 設定を JSON で保存する(日付・パスなどの文字以外の値も文字にして保存する)。
def save_run_settings(run_dir: Path, settings: dict) -> Path:
    path = Path(run_dir) / "run_settings.json"
    data = {"作成日時": datetime.now().isoformat(timespec="seconds"), **settings}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path
