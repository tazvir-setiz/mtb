from app.telegram.channel_service import normalize_channel_ref


def test_normalize_username():
    assert normalize_channel_ref("@my_channel") == "@my_channel"


def test_normalize_plain_username():
    assert normalize_channel_ref("my_channel") == "@my_channel"


def test_normalize_numeric_id():
    assert normalize_channel_ref("-1001234567890") == -1001234567890


def test_normalize_link():
    assert normalize_channel_ref("https://t.me/my_channel") == "@my_channel"
