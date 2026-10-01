from app.services.guard.contracts import validate_meaning_verdict


def test_verification_accepts_missing_repairable_on_failure():
    v = validate_meaning_verdict('{"passed":false,"issues":["meaning changed"]}')
    assert v.repairable is True


def test_verification_pass_forces_repairable_false():
    v = validate_meaning_verdict('{"passed":true,"issues":[],"repairable":false}')
    assert v.passed
    assert v.repairable is False
