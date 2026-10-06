import sys
from pathlib import Path

import nbformat

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "notebooks"))
import build_notebook  # noqa: E402
import update_notebook  # noqa: E402


def test_carry_over_keeps_user_values_and_reports_changes():
    old = 'INPUT_DIR = "D:/mine"\nTOPIC_NAME = "SHAPE"\nKEYWORDS = [\n    "a",\n    "b",\n]\nOLD_ONLY = 1\nNOTEBOOK_VERSION = "old"\n'
    new = '# 版\nNOTEBOOK_VERSION = "new"\nINPUT_DIR = "../data"\n# 名前\nTOPIC_NAME = "TOTAL"\nKEYWORDS = ["x"]\nNEW_ONLY = 2\n'
    merged, carried, added, dropped = update_notebook.carry_over_settings(old, new)
    ns = {}
    exec(merged, ns)
    assert ns["INPUT_DIR"] == "D:/mine" and ns["TOPIC_NAME"] == "SHAPE" and ns["KEYWORDS"] == ["a", "b"]  # 複数行の値も引き継ぐ
    assert ns["NEW_ONLY"] == 2 and ns["NOTEBOOK_VERSION"] == "new"  # 新しい設定と版は、新しい値のまま
    assert "# 版" in merged and "# 名前" in merged  # コメントは新しいものが残る
    assert carried == ["INPUT_DIR", "KEYWORDS", "TOPIC_NAME"] and added == ["NEW_ONLY"] and dropped == ["OLD_ONLY"]


def test_update_notebook_end_to_end(tmp_path):
    # 古いコードで、設定を書き換えた手元のノートブックを作る
    old_nb = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(c.source) if c.cell_type == "code"
                                             else nbformat.v4.new_markdown_cell(c.source) for c in build_notebook.nb.cells])
    for c in old_nb.cells:
        if c.cell_type == "code" and "TOPIC_DEFINITION" in c.source and "TOPIC_NAME =" in c.source:
            c.source = (c.source.replace('INPUT_DIR = "../data"', 'INPUT_DIR = "D:/patents"')
                        .replace('TOPIC_NAME = "TOTAL-RNA-seq"', 'TOPIC_NAME = "SHAPE法"')
                        .replace(build_notebook.VERSION, "0000000"))
        elif c.cell_type == "code" and "def evaluate_table" in c.source:
            c.source = "# 古いコード\n" + c.source.replace("check_texts", "old_check")  # 古い版を模擬
    path = tmp_path / "my_run.ipynb"
    nbformat.write(old_nb, path)
    backup = update_notebook.update(path)
    new = nbformat.read(path, as_version=4)
    settings = next(c.source for c in new.cells if c.cell_type == "code" and "TOPIC_DEFINITION" in c.source and "TOPIC_NAME =" in c.source)
    assert 'INPUT_DIR = "D:/patents"' in settings and 'TOPIC_NAME = "SHAPE法"' in settings  # 設定は引き継ぐ
    assert f'NOTEBOOK_VERSION = "{build_notebook.VERSION}"' in settings  # 版は新しい
    code = "".join(c.source for c in new.cells if c.cell_type == "code")
    assert "# 古いコード" not in code and "def check_texts" in code  # コードは最新になる
    assert backup.exists() and backup.name.startswith("my_run_backup_")
    assert "# 古いコード" in "".join(c.source for c in nbformat.read(backup, as_version=4).cells if c.cell_type == "code")
