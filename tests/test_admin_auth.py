from app.config import settings


def test_only_configured_admins_are_authorized():
    assert settings.is_admin(111)
    assert settings.is_admin(222)
    for random_id in (1, 999999, -5):
        assert not settings.is_admin(random_id)
