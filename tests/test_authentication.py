import pytest
from fastapi.testclient import TestClient

from app.core.business_domains import AuthenticationError, user_from_token
from app.main import app


client = TestClient(app)


def test_frontend_entrypoint_serves_current_role_isolation_script():
    index = client.get("/")
    assert index.status_code == 200
    assert '/app.js?v=p0-product-4' in index.text

    script = client.get("/app.js?v=p0-product-4")
    assert script.status_code == 200
    assert "function resetAssistantSession(clearQueryLog)" in script.text
    assert 'if (hasFeature("knowledge"))' in script.text
    assert "当前库无专业—课程归属，按该专业学生选课覆盖统计" in script.text


@pytest.mark.parametrize("token", [None, "", "   ", "not-a-real-user"])
def test_user_from_token_rejects_missing_blank_and_unknown_tokens(token):
    with pytest.raises(AuthenticationError, match="未登录或令牌无效"):
        user_from_token(token)


def test_user_from_token_keeps_known_role_identity():
    ctx = user_from_token("student")
    assert ctx.username == "student"
    assert ctx.role == "student"
    assert ctx.row_scope == {"student_id": 1}


@pytest.mark.parametrize("headers", [{}, {"X-Demo-Token": "not-a-real-user"}])
def test_auth_session_returns_401_without_valid_token(headers):
    response = client.get("/api/auth/session", headers=headers)
    assert response.status_code == 401
    assert response.json() == {"detail": "未登录或令牌无效"}


def test_auth_session_restores_known_user():
    response = client.get("/api/auth/session", headers={"X-Demo-Token": "teacher"})
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "teacher"


def test_public_auth_bootstrap_endpoints_remain_accessible():
    assert client.get("/api/health").status_code == 200
    options = client.get("/api/auth/options")
    assert options.status_code == 200
    assert options.json()["users"]
    invalid_login = client.post(
        "/api/auth/login",
        json={"username": "missing-user", "password": "wrong-password"},
    )
    assert invalid_login.status_code == 401
    assert "用户名或密码错误" in invalid_login.json()["detail"]


def test_ask_rejects_missing_token_before_model_call():
    response = client.post(
        "/api/ask",
        json={"question": "平均成绩是多少？", "source": "teaching"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "未登录或令牌无效"}


def test_data_access_rejects_missing_token_instead_of_using_admin():
    response = client.get("/api/data-access/sources")
    assert response.status_code == 401
    assert response.json() == {"detail": "未登录或令牌无效"}


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("GET", "/api/profile?source=teaching", None),
        ("PUT", "/api/profile?source=teaching", {"profile": {}}),
        ("GET", "/api/profile/versions?source=teaching", None),
        ("POST", "/api/profile/publish?source=teaching", {}),
        ("POST", "/api/profile/rollback?source=teaching", {"version_id": "missing"}),
        ("PUT", "/api/profile/versions/missing?source=teaching", {"label": "x", "description": ""}),
        ("DELETE", "/api/profile/versions/missing?source=teaching", None),
        ("GET", "/api/quality?source=teaching", None),
    ],
)
def test_all_knowledge_management_endpoints_reject_student(method, path, payload):
    response = client.request(
        method,
        path,
        headers={"X-Demo-Token": "student"},
        json=payload,
    )
    assert response.status_code == 403
    assert "无权使用该功能" in response.json()["detail"]


@pytest.mark.parametrize(
    "path",
    [
        "/api/profile?source=teaching",
        "/api/profile/versions?source=teaching",
        "/api/quality?source=teaching",
    ],
)
def test_knowledge_reader_allows_college_manager(path):
    response = client.get(path, headers={"X-Demo-Token": "college"})
    assert response.status_code == 200


def test_profile_write_does_not_call_storage_for_student(monkeypatch):
    import app.api.routes as api_routes

    calls = []
    monkeypatch.setattr(
        api_routes,
        "save_profile_dict",
        lambda source, profile: calls.append((source, profile)) or profile,
    )
    body = {"profile": {"tables": {}, "columns": {}, "relations": [], "metrics": {}}}

    denied = client.put(
        "/api/profile?source=teaching",
        headers={"X-Demo-Token": "student"},
        json=body,
    )
    assert denied.status_code == 403
    assert calls == []

    allowed = client.put(
        "/api/profile?source=teaching",
        headers={"X-Demo-Token": "college"},
        json=body,
    )
    assert allowed.status_code == 200
    assert calls == [("teaching", body["profile"])]


def test_governance_read_requires_governance_feature():
    assert client.get("/api/governance/settings").status_code == 401
    assert client.get(
        "/api/governance/settings",
        headers={"X-Demo-Token": "student"},
    ).status_code == 403
    assert client.get(
        "/api/governance/settings",
        headers={"X-Demo-Token": "jwc"},
    ).status_code == 403
    assert client.get(
        "/api/governance/settings",
        headers={"X-Demo-Token": "admin"},
    ).status_code == 200


def test_governance_write_does_not_call_storage_without_feature(monkeypatch):
    import app.api.governance as governance_api

    calls = []
    monkeypatch.setattr(
        governance_api,
        "save_settings",
        lambda payload: calls.append(payload) or payload,
    )

    denied = client.put(
        "/api/governance/settings",
        headers={"X-Demo-Token": "student"},
        json={},
    )
    assert denied.status_code == 403
    assert calls == []

    allowed = client.put(
        "/api/governance/settings",
        headers={"X-Demo-Token": "admin"},
        json={},
    )
    assert allowed.status_code == 200
    assert calls == [{}]


def test_low_confidence_queue_requires_ask_but_not_governance(monkeypatch):
    import app.api.governance as governance_api

    calls = []
    monkeypatch.setattr(
        governance_api,
        "create_low_confidence_review",
        lambda payload: calls.append(payload) or {"id": "controlled-review"},
    )
    payload = {"question": "平均成绩是多少？", "confidence": 50}

    missing = client.post("/api/governance/review-items/low-confidence", json=payload)
    assert missing.status_code == 401
    assert calls == []

    student = client.post(
        "/api/governance/review-items/low-confidence",
        headers={"X-Demo-Token": "student"},
        json=payload,
    )
    assert student.status_code == 200
    assert student.json()["queued"] is True
    assert calls == [payload]


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("GET", "/api/feedback?source=teaching", None),
        ("POST", "/api/feedback", {"kind": "incorrect", "question": "controlled", "sql": "SELECT 1", "source": "teaching"}),
        ("DELETE", "/api/feedback/memory-feedback", None),
        ("GET", "/api/examples?source=teaching", None),
        ("POST", "/api/examples?source=teaching", {"id": "memory-example", "question": "controlled", "sql": "SELECT 1"}),
        ("DELETE", "/api/examples/memory-example?source=teaching", None),
    ],
)
def test_feedback_and_example_endpoints_reject_missing_token_before_storage(
    monkeypatch,
    method,
    path,
    payload,
):
    import app.api.routes as api_routes

    def fail_if_called(*args, **kwargs):
        pytest.fail(f"storage function called before authentication: args={args}, kwargs={kwargs}")

    for name in (
        "add_feedback",
        "create_feedback_review",
        "list_feedback",
        "delete_feedback",
        "delete_review_items_for_feedback",
        "list_examples",
        "upsert_example",
        "delete_example",
    ):
        monkeypatch.setattr(api_routes, name, fail_if_called)

    response = client.request(method, path, json=payload)
    assert response.status_code == 401
    assert response.json() == {"detail": "未登录或令牌无效"}


def test_feedback_permissions_keep_ask_workflow_and_protect_management_list(monkeypatch):
    import app.api.routes as api_routes

    calls = []
    feedback = {
        "id": "memory-feedback",
        "kind": "incorrect",
        "question": "controlled",
        "sql": "SELECT 1",
        "source": "teaching",
    }
    monkeypatch.setattr(
        api_routes,
        "add_feedback",
        lambda payload: calls.append(("add", payload["question"])) or {**feedback, **payload},
    )
    monkeypatch.setattr(
        api_routes,
        "create_feedback_review",
        lambda item: calls.append(("review", item["id"])) or {"id": "memory-review"},
    )
    monkeypatch.setattr(
        api_routes,
        "list_feedback",
        lambda source, limit: calls.append(("list", source, limit)) or [feedback],
    )
    monkeypatch.setattr(
        api_routes,
        "delete_feedback",
        lambda item_id: calls.append(("delete", item_id)) or feedback,
    )
    monkeypatch.setattr(
        api_routes,
        "delete_review_items_for_feedback",
        lambda item_id: calls.append(("delete_reviews", item_id)) or 1,
    )

    student_headers = {"X-Demo-Token": "student"}
    denied_list = client.get("/api/feedback?source=teaching", headers=student_headers)
    assert denied_list.status_code == 403
    assert calls == []

    created = client.post(
        "/api/feedback",
        headers=student_headers,
        json={"kind": "incorrect", "question": "controlled", "sql": "SELECT 1", "source": "teaching"},
    )
    assert created.status_code == 200
    assert calls == [("add", "controlled"), ("review", "memory-feedback")]

    removed = client.delete("/api/feedback/memory-feedback", headers=student_headers)
    assert removed.status_code == 200
    assert removed.json()["deleted_reviews"] == 1
    assert calls[-2:] == [("delete", "memory-feedback"), ("delete_reviews", "memory-feedback")]

    managed = client.get(
        "/api/feedback?source=teaching",
        headers={"X-Demo-Token": "college"},
    )
    assert managed.status_code == 200
    assert managed.json()["items"][0]["id"] == "memory-feedback"
    assert calls[-1] == ("list", "teaching", 100)


def test_example_permissions_allow_ask_read_and_require_knowledge_for_writes(monkeypatch):
    import app.api.routes as api_routes

    calls = []
    example = {
        "id": "memory-example",
        "source": "teaching",
        "question": "controlled",
        "sql": "SELECT 1",
    }
    monkeypatch.setattr(
        api_routes,
        "list_examples",
        lambda source, limit: calls.append(("list", source, limit)) or [example],
    )
    monkeypatch.setattr(
        api_routes,
        "upsert_example",
        lambda source, payload: calls.append(("upsert", source, payload["id"])) or {**example, **payload},
    )
    monkeypatch.setattr(
        api_routes,
        "delete_example",
        lambda source, item_id: calls.append(("delete", source, item_id)),
    )

    student_headers = {"X-Demo-Token": "student"}
    readable = client.get("/api/examples?source=teaching", headers=student_headers)
    assert readable.status_code == 200
    assert readable.json()["items"][0]["id"] == "memory-example"
    assert calls == [("list", "teaching", 200)]

    payload = {"id": "memory-example", "question": "controlled", "sql": "SELECT 1"}
    denied_save = client.post(
        "/api/examples?source=teaching",
        headers=student_headers,
        json=payload,
    )
    denied_delete = client.delete(
        "/api/examples/memory-example?source=teaching",
        headers=student_headers,
    )
    assert denied_save.status_code == 403
    assert denied_delete.status_code == 403
    assert calls == [("list", "teaching", 200)]

    manager_headers = {"X-Demo-Token": "college"}
    saved = client.post(
        "/api/examples?source=teaching",
        headers=manager_headers,
        json=payload,
    )
    removed = client.delete(
        "/api/examples/memory-example?source=teaching",
        headers=manager_headers,
    )
    assert saved.status_code == 200
    assert removed.status_code == 200
    assert calls[-2:] == [
        ("upsert", "teaching", "memory-example"),
        ("delete", "teaching", "memory-example"),
    ]
