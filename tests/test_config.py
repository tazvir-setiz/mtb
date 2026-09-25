from app.config import settings, _parse_admin_ids


def test_admin_ids_parsed():
    assert 111 in settings.admin_ids
    assert 222 in settings.admin_ids


def test_is_admin():
    assert settings.is_admin(111) is True
    assert settings.is_admin(999) is False


def test_default_values_loaded():
    assert settings.bot_token
    assert settings.api_id == 12345
    assert settings.forward_delay >= 0


def test_parse_admin_ids_plain():
    assert _parse_admin_ids("123456789") == [123456789]


def test_parse_admin_ids_comma_separated():
    assert _parse_admin_ids("123456789,987654321") == [123456789, 987654321]


def test_parse_admin_ids_comma_with_spaces():
    assert _parse_admin_ids("123456789, 987654321") == [123456789, 987654321]


def test_parse_admin_ids_json_style():
    assert _parse_admin_ids("[123456789, 987654321]") == [123456789, 987654321]


def test_parse_admin_ids_json_style_with_quoted_strings():
    assert _parse_admin_ids('["123456789", "987654321"]') == [123456789, 987654321]


def test_parse_admin_ids_quoted_whole_value():
    assert _parse_admin_ids('"123456789"') == [123456789]
    assert _parse_admin_ids("'123456789'") == [123456789]


def test_parse_admin_ids_empty():
    assert _parse_admin_ids("") == []
    assert _parse_admin_ids("   ") == []


def test_parse_admin_ids_ignores_bad_items_only():
    assert _parse_admin_ids("123456789,abc,987654321") == [123456789, 987654321]
