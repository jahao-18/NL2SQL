from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.business_domains import (
    AuthenticationError,
    AuthorizationError,
    require_admin,
    token_for,
    user_from_token,
)
from app.core.config import ROOT_DIR, settings
from app.core.data_sources import _normalized_sqlite_url, load_sources
from app.core.schema import list_table_names
from app.core.schema_profile import _version_yaml_path
from app.core.validator import SQLValidationError, validate_and_fix
from app.main import app


def test_signed_demo_token_rejects_missing_and_forged_values():
    with pytest.raises(AuthenticationError):
        user_from_token(None)
    with pytest.raises(AuthenticationError):
        user_from_token("admin")
    with pytest.raises(AuthenticationError):
        user_from_token("YWRtaW4.invalid")
    assert user_from_token(token_for("student")).username == "student"


def test_admin_guard_rejects_non_admin_role():
    assert require_admin(token_for("admin")).is_admin
    with pytest.raises(AuthorizationError):
        require_admin(token_for("teacher"))


def test_auth_api_requires_login_and_accepts_login_token():
    with TestClient(app) as client:
        assert client.get("/api/auth/session").status_code == 401
        login = client.post("/api/auth/login", json={"username": "student", "password": "123456"})
        assert login.status_code == 200
        token = login.json()["token"]
        session = client.get("/api/auth/session", headers={"X-Demo-Token": token})
        assert session.status_code == 200
        assert session.json()["user"]["username"] == "student"


def test_profile_write_requires_admin():
    with TestClient(app) as client:
        response = client.put(
            "/api/profile?source=teaching",
            headers={"X-Demo-Token": token_for("student")},
            json={"profile": {}},
        )
        assert response.status_code == 403


def test_version_id_blocks_path_traversal():
    with pytest.raises(ValueError, match="非法版本号"):
        _version_yaml_path("teaching", r"..\..\teaching")


@pytest.mark.parametrize(
    ("sql", "scope"),
    [
        ("SELECT COUNT(*) FROM enrollment", {"student_id": 1}),
        ("SELECT COUNT(*) FROM teaching_class", {"teacher_id": 37}),
        ("SELECT COUNT(*) FROM student", {"college_id": 1}),
    ],
)
def test_row_scope_rejects_queries_without_required_predicate(sql, scope):
    allowed = {
        "enrollment": ["id", "student_id"],
        "teaching_class": ["id", "teacher_id"],
        "student": ["id", "college_id"],
    }
    with pytest.raises(SQLValidationError, match="必须限定"):
        validate_and_fix(sql, allowed, row_scope=scope)


@pytest.mark.parametrize(
    ("sql", "scope"),
    [
        ("SELECT COUNT(*) FROM enrollment e WHERE e.student_id = 1", {"student_id": 1}),
        ("SELECT COUNT(*) FROM teaching_class tc WHERE tc.teacher_id = 37", {"teacher_id": 37}),
        ("SELECT COUNT(*) FROM student s WHERE s.college_id = 1", {"college_id": 1}),
    ],
)
def test_row_scope_accepts_matching_predicate(sql, scope):
    allowed = {
        "enrollment": ["id", "student_id"],
        "teaching_class": ["id", "teacher_id"],
        "student": ["id", "college_id"],
    }
    fixed, _ = validate_and_fix(sql, allowed, row_scope=scope)
    assert fixed.endswith(f"LIMIT {settings.max_rows}")


def test_relative_sqlite_url_is_rooted_at_project_directory():
    normalized = _normalized_sqlite_url("sqlite:///data/teaching.db")
    assert (ROOT_DIR / "data" / "teaching.db").resolve().as_posix() in normalized


def test_configured_bird_databases_when_dataset_is_available():
    root = Path(settings.bird_database_root)
    if not root.is_absolute():
        root = ROOT_DIR / root
    if not root.exists():
        pytest.skip("本机未安装 BIRD 数据集")
    names = [name for name in load_sources() if name != "teaching"]
    assert names
    assert all(list_table_names(name) for name in names)
