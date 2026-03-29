"""Tests for lead-capture notification helpers."""

from services import lead_capture_notifications


def test_build_lead_thank_you_message_for_browse_directory():
    message = lead_capture_notifications.build_lead_thank_you_message("browse_directory")
    assert "vendor directory" in message
    assert lead_capture_notifications.BOOK_TIME_URL in message


def test_build_discord_notification_content_for_advisory_follow_up():
    content = lead_capture_notifications.build_discord_notification_content(
        {
            "lead_name": "Taylor",
            "company_name": "Example",
            "lead_email": "taylor@example.com",
            "lead_intent": "advisory_follow_up",
            "entry_page": "landing.html",
        }
    )
    assert "Advisory follow-up with SuccessByCS" in content
    assert lead_capture_notifications.BOOK_TIME_URL in content


def test_trigger_lead_capture_notification_posts_to_expected_webhook():
    captured = {}

    def fake_post(path, payload):
        captured["path"] = path
        captured["payload"] = payload
        return {"ok": True, "discord_sent": True}

    result = lead_capture_notifications.trigger_lead_capture_notification(
        {
            "lead_id": "lead-1",
            "lead_name": "Taylor",
            "lead_email": "taylor@example.com",
            "company_name": "Example",
            "lead_intent": "browse_directory",
            "intent_category": "content",
        },
        post_webhook_fn=fake_post,
    )

    assert captured["path"] == "csp-lead-capture-intake"
    assert captured["payload"]["booking_url"] == lead_capture_notifications.BOOK_TIME_URL
    assert result["triggered"] is True
