from patent_search.platpat import google_patent_id, parse_text

SAMPLE = """検索結果一覧(国内文献)
No.
文献番号
FI
1

特開2026-139649

特願2026-077513

2026/05/01

2026/09/01

ライダーシステム

オーロラ

審査中
公開公報の発行

G01S7/481@A

2

特許7880185

特願2026-007548

2026/01/20

2026/06/25

システム

株式会社上智

他

特許 有効
登録公報の発行

G06Q50/10
G06Q50/26
他

3

再表2015/072306

PCT/JP2014/000001

2014/01/01

2015/05/21

名称

出願人

-

C08L7/00

Copyright JPO and INPIT
(P0115)
"""


def test_parse_records():
    rows = parse_text(SAMPLE)
    assert [r.doc_no for r in rows] == ["特開2026-139649", "特許7880185", "再表2015/072306"]
    assert rows[0].status == ["審査中", "公開公報の発行"] and rows[0].fi == ["G01S7/481@A"]
    assert rows[1].applicant_has_more and rows[1].fi_has_more and len(rows[1].fi) == 2
    assert rows[2].status == ["-"] and rows[2].fi == ["C08L7/00"] and not rows[2].warnings


def test_google_id():
    assert google_patent_id("特開2026-139649") == "JP2026139649A"
    assert google_patent_id("特開昭50-051518") == "JPS50051518A"
    assert google_patent_id("特開平05-123456") == "JPH05123456A"
    assert google_patent_id("再表2015/072306") == "JPWO2015072306A1"
    assert google_patent_id("再表92/019759") == "JPWO1992019759A1"
    assert google_patent_id("不明") == ""
