from nyayabrief.prefilter import prefilter


def test_legal_passes():
    assert prefilter("SC grants bail", "The Supreme Court granted bail under Article 21.").passed


def test_sports_skipped():
    assert not prefilter("India beat Australia", "A thrilling match at the stadium.", "SPORT").passed


def test_generic_news_fails():
    assert not prefilter("Monsoon arrives early", "Rains lashed the city on Monday.").passed
