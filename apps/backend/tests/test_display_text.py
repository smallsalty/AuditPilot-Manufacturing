from app.utils.display_text import clean_document_title


def test_clean_document_title_removes_highlight_html_and_duplicates() -> None:
    title = "<em>2025年</em>半<em>年度报告</em><em>2025年</em>半<em>年度报告</em><em>摘要</em>"

    cleaned = clean_document_title(title)

    assert cleaned == "2025年半年度报告摘要"
