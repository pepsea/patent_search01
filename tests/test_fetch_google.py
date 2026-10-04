from patent_search.fetch_google import extract

# Google Patents の構造を想定した最小の模擬 HTML（実ページでの検証は未実施）
HTML = """<html><body><h1><span itemprop="title">電池システム</span> - Google Patents</h1>
<section itemprop="abstract"><div class="abstract">要約です</div></section>
<section itemprop="description"><p>0001 明細書の段落</p></section>
<section itemprop="claims"><div class="claim">【請求項１】A</div><div class="claim">【請求項２】B</div></section>
</body></html>"""


def test_extract():
    x = extract(HTML)
    assert x["title"] == "電池システム" and x["claim_count"] == 2 and x["extract_status"] == "OK"


def test_extract_reports_missing():
    assert "欠落" in extract("<html><body></body></html>")["extract_status"]
