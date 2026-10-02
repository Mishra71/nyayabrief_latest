from nyayabrief.prefilter import prefilter


def test_legal_passes():
    assert prefilter("SC grants bail", "The Supreme Court granted bail under Article 21.").passed


def test_sports_skipped():
    assert not prefilter("India beat Australia", "A thrilling match at the stadium.", "SPORT", min_score=2).passed


def test_generic_news_fails():
    assert not prefilter("Monsoon arrives early", "Rains lashed the city on Monday.", min_score=2).passed


def test_current_affairs_passes():
    r = prefilter("China hints at cancelling U.S. tariffs", "The Chinese Commerce Ministry said both sides agreed to cancel tariffs in a phase one trade deal.")
    assert r.passed


def test_cyclone_passes():
    assert prefilter("Bulbul likely to bring heavy rain", "The cyclonic storm over the Bay of Bengal; NDRF teams were sent to coastal districts as a disaster precaution.").passed


def test_default_is_permissive_but_junk_is_dropped():
    assert prefilter("Monsoon arrives early", "Rains lashed the city on Monday.").passed
    assert not prefilter("THE HINDU CROSSWORD 12775", "1 Article with a picture originally relating to a medical condition").passed
