from __future__ import annotations

import pytest

from app.core import governance


@pytest.fixture()
def isolated_governance(tmp_path, monkeypatch):
    monkeypatch.setattr(governance, "SETTINGS_PATH", tmp_path / "settings.yaml")
    monkeypatch.setattr(governance, "REVIEW_ITEMS_PATH", tmp_path / "review_items.jsonl")
    return tmp_path


def test_error_feedback_respects_auto_queue_setting(isolated_governance):
    feedback = {
        "id": "fb1",
        "kind": "incorrect",
        "source": "demo",
        "source_label": "Demo",
        "question": "wrong answer",
        "sql": "SELECT 1",
        "reason": "field mismatch",
    }

    governance.save_settings({"auto_queue_error_feedback": False})
    assert governance.create_feedback_review(feedback) is None
    assert governance.list_review_items(status="all") == []

    governance.save_settings({"auto_queue_error_feedback": True})
    item = governance.create_feedback_review(feedback)
    assert item is not None
    assert item["type"] == "feedback_fix"
    assert governance.list_review_items(status="open")[0]["payload"]["feedback"]["id"] == "fb1"


def test_publish_review_is_approved_before_publish(isolated_governance, monkeypatch):
    monkeypatch.setattr(governance, "load_profile_dict", lambda source: {"tables": {"orders": {}}, "relations": [], "metrics": {}})
    monkeypatch.setattr(governance, "save_profile_dict", lambda source, profile: profile)
    published = {}

    def fake_publish(source, label="", description=""):
        published.update({"source": source, "label": label, "description": description})
        return {"published": True, **published}

    monkeypatch.setattr(governance, "publish_profile", fake_publish)

    item = governance.create_publish_review("demo", label="v1", description="release note")
    assert item["type"] == "profile_publish"
    assert published == {}

    result = governance.accept_review_item(item["id"], "publish_profile", {"source": "demo"})
    assert result["item"]["status"] == "accepted"
    assert published == {"source": "demo", "label": "v1", "description": "release note"}


def test_low_confidence_review_uses_threshold(isolated_governance):
    governance.save_settings({"low_confidence_threshold": 80})
    high = governance.create_low_confidence_review({"confidence": 85, "source": "demo", "question": "ok"})
    low = governance.create_low_confidence_review({
        "confidence": 50,
        "source": "demo",
        "source_label": "Demo",
        "question": "check this",
        "sql": "SELECT 1",
    })
    assert high is None
    assert low is not None
    assert low["priority"] == "high"
    assert low["category"] == "low_confidence"
