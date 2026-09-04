from unittest.mock import patch

import pytest
import requests

from watchtower.notifiers import SlackNotifier, build_notifiers


def test_slack_notifier_requires_webhook():
    with pytest.raises(ValueError):
        SlackNotifier(webhook_url="")


@patch("watchtower.notifiers.requests.post")
def test_slack_notifier_sends_post(mock_post):
    mock_post.return_value.raise_for_status = lambda: None
    notifier = SlackNotifier(webhook_url="https://hooks.slack.example/xyz")
    notifier.send("cpu breach")

    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    assert kwargs["json"] == {"text": "cpu breach"}


@patch("watchtower.notifiers.requests.post", side_effect=requests.RequestException("timeout"))
def test_slack_notifier_failure_does_not_raise(mock_post):
    notifier = SlackNotifier(webhook_url="https://hooks.slack.example/xyz")
    notifier.send("cpu breach")  # must not raise


def test_build_notifiers_from_config():
    cfg = {"console": {"enabled": True}, "slack": {"enabled": False}}
    notifiers = build_notifiers(cfg)
    assert len(notifiers) == 1
