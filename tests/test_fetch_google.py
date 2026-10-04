from patent_search.fetch_google import extract

# 実ページ(JP2017080742A/ja)の構造を最小化したもの
HTML = """<html><body><h1 itemprop="pageTitle">JP2017080742A - 電池 - Google Patents</h1>
<span itemprop="title">電池システム
   </span>
<section itemprop="abstract"><h2>Abstract</h2><div itemprop="content"><abstract><div class="abstract">要約です</div></abstract></div></section>
<section itemprop="description"><h2>Description</h2><div itemprop="content"><div class="description">
<div class="description-paragraph" num="0001"> 明細書の<u>段落</u>です </div>
<div class="description-paragraph" num="0002"> 二つ目 </div></div></div></section>
<section itemprop="claims"><h2>Claims (2)</h2><div itemprop="content"><ol class="claims">
<li class="claim"><div class="claim" num="1"><div class="claim-text">Ａ<u>を</u>備え、<br/>Ｌ<sub>f</sub>である</div></div></li>
<li class="claim-dependent"><div class="claim" num="2"><div class="claim-text">請求項１のＢ</div></div></li>
</ol></div></section></body></html>"""


def test_extract():
    x = extract(HTML)
    assert x["title"] == "電池システム"
    assert x["claim_count"] == 2  # li と div の二重取りをしない
    assert x["claims"].startswith("【請求項1】Ａを備え、\nＬfである")
    assert x["abstract"] == "要約です"  # 見出し Abstract を含めない
    assert x["description"].splitlines()[0] == "[0001] 明細書の段落です"
    assert x["extract_status"] == "OK"


def test_extract_reports_missing():
    assert "欠落" in extract("<html><body></body></html>")["extract_status"]
