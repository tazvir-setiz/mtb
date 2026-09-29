from app.services.guard.contracts import validate_verification


def test_verification_accepts_missing_repairable_on_failure():
    v = validate_verification(
        '{"policy_pass":false,"meaning_preserved":false,'
        '"issues":["meaning changed"]}'
    )
    assert v.repairable is True


def test_verification_pass_forces_repairable_false():
    v = validate_verification(
        '{"policy_pass":true,"meaning_preserved":true,"issues":[],"repairable":false}'
    )
    assert v.passed
    assert v.repairable is False
