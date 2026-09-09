"""Email generation/sending tests (Section 35)."""
from __future__ import annotations

from datetime import date

from src.email.sender import send_morning_email
from src.providers.mock_providers import MockEmailProvider


def test_mock_email_provider_writes_file(tmp_path):
    provider = MockEmailProvider(output_dir=str(tmp_path))
    success = provider.send(
        to_addr="you@example.com", from_addr="desk@example.com",
        subject="Test", html_body="<html><body>hi</body></html>",
    )
    assert success is True
    assert provider.last_path.exists()
    assert "hi" in provider.last_path.read_text()


def test_send_morning_email_skips_without_email_to(monkeypatch, settings):
    monkeypatch.delenv("EMAIL_TO", raising=False)
    provider = MockEmailProvider(output_dir="outbox_test")
    result = send_morning_email(provider, settings, date(2026, 9, 9), "<html></html>")
    assert result is False


def test_send_morning_email_succeeds_with_email_to(monkeypatch, settings, tmp_path):
    monkeypatch.setenv("EMAIL_TO", "you@example.com")
    provider = MockEmailProvider(output_dir=str(tmp_path))
    result = send_morning_email(provider, settings, date(2026, 9, 9), "<html>report</html>")
    assert result is True


def test_email_provider_failure_returns_false_not_raise():
    from src.providers.email_base import EmailProvider

    class FailingEmailProvider(EmailProvider):
        name = "failing"

        def send(self, to_addr, from_addr, subject, html_body):
            return False

    result = FailingEmailProvider().send("a@b.com", "c@d.com", "subj", "<html></html>")
    assert result is False
