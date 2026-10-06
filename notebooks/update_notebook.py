"""手元のノートブックを、最新のコードに更新する。設定セルで書き換えた値は引き継ぐ。

使い方:
    python notebooks/update_notebook.py 手元のノートブック.ipynb

- 手元のノートブックを、バックアップ(元の名前に _backup_日時 を付けたファイル)に残してから、最新のコードで上書きする。
- 設定セルの値(INPUT_DIR、TOPIC_* など)は、同じ名前の設定があれば引き継ぐ。新しく増えた設定は、初期値のまま。
- なぜ必要か: ノートブックはコードを中に埋め込んでいる。リポジトリを更新(git pull)しても、手元で設定を書き換えた
  ノートブックは、古いコードのままか、更新時に競合する。手元用のノートブックは、リポジトリのファイルとは別の名前で
  保存し(例: notebooks/my_run.ipynb)、更新のたびにこのスクリプトを使う。
"""

from __future__ import annotations

import ast
import shutil
import sys
from datetime import datetime
from pathlib import Path

import nbformat

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_notebook  # noqa: E402  最新のコードで作ったノートブック(build_notebook.nb)を使う

# 引き継がない設定(コードの版など、ノートブックが自動で決める値)
NOT_CARRIED = {"NOTEBOOK_VERSION"}


def _assignments(source: str) -> dict[str, ast.Assign]:
    """設定セルの先頭レベルの「名前 = 値」を、名前ごとに集める。"""
    found = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            found[node.targets[0].id] = node
    return found


def carry_over_settings(old_source: str, new_source: str) -> tuple[str, list[str], list[str], list[str]]:
    """古い設定セルの値を、新しい設定セルに引き継ぐ。

    戻り値: (引き継いだ後の設定セル, 引き継いだ名前, 新しく増えた設定の名前, 新しいノートブックに無くなった設定の名前)
    """
    old, new = _assignments(old_source), _assignments(new_source)
    lines = new_source.splitlines(keepends=True)
    carried = []
    # 後ろの行から置き換える(前の行の位置がずれないように)
    for name, node in sorted(new.items(), key=lambda kv: kv[1].lineno, reverse=True):
        if name in old and name not in NOT_CARRIED:
            text = ast.get_source_segment(old_source, old[name])
            lines[node.lineno - 1: node.end_lineno] = [text + "\n"]
            carried.append(name)
    added = [n for n in new if n not in old and n not in NOT_CARRIED]
    dropped = [n for n in old if n not in new]
    return "".join(lines), sorted(carried), added, dropped


def _settings_cell(nb) -> int:
    for i, c in enumerate(nb.cells):
        if c.cell_type == "code" and "TOPIC_NAME =" in c.source and "TOPIC_DEFINITION" in c.source:
            return i
    raise ValueError("設定のセル(TOPIC_NAME と TOPIC_DEFINITION を含むセル)が見つかりません")


def update(path: str | Path) -> Path:
    path = Path(path)
    old_nb = nbformat.read(path, as_version=4)
    new_nb = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(c.source) if c.cell_type == "code"
                                             else nbformat.v4.new_markdown_cell(c.source)
                                             for c in build_notebook.nb.cells], metadata=build_notebook.nb.metadata)
    i_old, i_new = _settings_cell(old_nb), _settings_cell(new_nb)
    merged, carried, added, dropped = carry_over_settings(old_nb.cells[i_old].source, new_nb.cells[i_new].source)
    new_nb.cells[i_new].source = merged

    backup = path.with_name(f"{path.stem}_backup_{datetime.now():%Y%m%d_%H%M%S}{path.suffix}")
    shutil.copy2(path, backup)
    nbformat.write(new_nb, path)
    print(f"更新しました: {path}  (版 {build_notebook.VERSION})")
    print(f"元のノートブックは、次の名前で残しました: {backup.name}")
    print(f"引き継いだ設定: {len(carried)} 件")
    if added:
        print("新しく増えた設定(初期値のまま。必要なら設定セルで確認してください):", ", ".join(added))
    if dropped:
        print("新しいノートブックには無い設定(引き継ぎません):", ", ".join(dropped))
    return backup


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    update(sys.argv[1])
