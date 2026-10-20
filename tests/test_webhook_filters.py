from src.webhook_filters import is_self_triggered


def test_bot_sender_without_login_filter_is_self_triggered():
    payload = {"sender": {"type": "Bot", "login": "my-github-app[bot]"}}

    assert is_self_triggered(payload) is True


def test_user_sender_is_not_self_triggered():
    payload = {"sender": {"type": "User", "login": "someone"}}

    assert is_self_triggered(payload) is False


def test_bot_sender_matching_expected_login_is_self_triggered():
    payload = {"sender": {"type": "Bot", "login": "my-github-app[bot]"}}

    assert is_self_triggered(payload, app_bot_login="my-github-app[bot]") is True


def test_bot_sender_not_matching_expected_login_is_not_self_triggered():
    payload = {"sender": {"type": "Bot", "login": "some-other-app[bot]"}}

    assert is_self_triggered(payload, app_bot_login="my-github-app[bot]") is False


def test_missing_sender_is_not_self_triggered():
    payload = {}

    assert is_self_triggered(payload) is False
