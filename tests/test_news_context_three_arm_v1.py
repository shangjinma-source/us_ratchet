from scripts.research.run_news_context_three_arm_v1 import quote_in_source


def test_whitespace_only_contiguous_quote():
    assert quote_in_source('Actual delivery guidance', 'Actual\n delivery   guidance')
    assert not quote_in_source('Actual sales guidance', 'Actual delivery guidance')
    assert not quote_in_source('Actual guidance', 'Actual delivery guidance')
    assert not quote_in_source('Actual, delivery guidance', 'Actual delivery guidance')
    assert not quote_in_source('', 'Actual delivery guidance')
