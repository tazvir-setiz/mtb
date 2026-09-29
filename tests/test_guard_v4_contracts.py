from app.services.guard.contracts import (
    validate_meaning,
    validate_meaning_verdict,
    validate_policy_verdict,
)
from app.services.guard_models import Label


def test_new_labels_exist():
    assert Label.HATE.value == "HATE"
    assert Label.THREAT.value == "THREAT"


def test_meaning_decomposition_contract():
    value = validate_meaning(
        '{"protected_meaning":["سلام کردن"],'
        '"removable_meaning":["توهین"],'
        '"entities_relations":[],'
        '"ambiguities":[]}'
    )
    assert value.has_protected_meaning
    assert value.protected_meaning == ("سلام کردن",)


def test_policy_and_meaning_judges_are_independent_contracts():
    p = validate_policy_verdict(
        '{"passed":true,"issues":[],"repairable":false}'
    )
    m = validate_meaning_verdict(
        '{"passed":false,"issues":["negative polarity lost"],"repairable":true}'
    )
    assert p.passed
    assert not m.passed
    assert m.repairable
