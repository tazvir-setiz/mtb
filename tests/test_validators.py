from app.utils.validators import (
    is_admin_user,
    parse_id_list,
    validate_channel_input,
    validate_message_id,
    validate_range,
)


def test_is_admin_user():
    assert is_admin_user(111, [111, 222]) is True
    assert is_admin_user(999, [111, 222]) is False


def test_validate_channel_input_empty():
    assert validate_channel_input("") is not None


def test_validate_channel_input_valid():
    assert validate_channel_input("@my_channel") is None


def test_validate_message_id_valid():
    value, error = validate_message_id("150")
    assert value == 150
    assert error is None


def test_validate_message_id_invalid():
    value, error = validate_message_id("abc")
    assert value is None
    assert error is not None


def test_validate_message_id_zero():
    value, error = validate_message_id("0")
    assert value is None
    assert error is not None


def test_validate_range_ok():
    assert validate_range(100, 150) is None


def test_validate_range_invalid_order():
    assert validate_range(150, 100) is not None


def test_validate_range_too_large():
    assert validate_range(1, 100000) is not None


def test_parse_id_list_valid():
    ids, error = parse_id_list("101, 102,103")
    assert ids == [101, 102, 103]
    assert error is None


def test_parse_id_list_invalid():
    ids, error = parse_id_list("101, abc")
    assert ids is None
    assert error is not None
