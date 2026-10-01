from nyayabrief.grounding import validate
from nyayabrief.schemas import CaseInfo, Evidence, Extraction, LegalProvision

BODY = ("The Supreme Court on Tuesday granted bail to the accused, holding that prolonged incarceration violates "
        "Article 21 of the Constitution. A bench of Justice A and Justice B noted that 3 years had passed.")


def make(**kw):
    base = dict(
        summary="SC granted bail citing Article 21 after 3 years.",
        key_points=["Bail granted"], exam_relevance="Article 21 and speedy trial.",
        evidence=[Evidence(quote="prolonged incarceration violates Article 21 of the Constitution")],
    )
    base.update(kw)
    return Extraction(**base)


def test_verified_when_all_grounded():
    v = validate(make(provisions=[LegalProvision(name="Article 21", kind="constitution")]), BODY)
    assert v.status == "verified" and v.warnings == []


def test_hallucinated_provision_and_case_are_dropped():
    ex = make(
        provisions=[LegalProvision(name="Article 21", kind="constitution"), LegalProvision(name="Section 999 IPC", kind="section")],
        case=CaseInfo(case_name="Maneka Gandhi v. Union of India", court="Supreme Court"),
    )
    v = validate(ex, BODY)
    assert v.status == "partial"
    assert [p.name for p in v.data.provisions] == ["Article 21"]
    assert v.data.case.case_name is None and v.data.case.court == "Supreme Court"


def test_fake_quote_and_no_evidence_needs_review():
    ex = make(evidence=[Evidence(quote="The court also ordered the state to pay compensation")])
    assert validate(ex, BODY).status == "needs_review"


def test_invented_number_flagged():
    v = validate(make(summary="SC granted bail after 7 years."), BODY)
    assert v.status == "partial" and any("numbers" in w for w in v.warnings)
