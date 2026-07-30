import sqlite3

from fastapi.testclient import TestClient

from app.core import teaching_migrations
from app.core.business_domains import token_for
from app.main import app


def _headers(username: str) -> dict[str, str]:
    return {"X-Demo-Token": token_for(username)}


def _reset_class(teaching_class_id: int) -> None:
    with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
        ids = [row[0] for row in conn.execute(
            "SELECT id FROM grade_submission WHERE teaching_class_id=?",
            (teaching_class_id,),
        )]
        for submission_id in ids:
            conn.execute("DELETE FROM grade_submission_detail WHERE grade_submission_id=?", (submission_id,))
        conn.execute("DELETE FROM grade_submission WHERE teaching_class_id=?", (teaching_class_id,))
        conn.commit()


def _csv(rows: list[dict], score: str = "88") -> str:
    return "学号,姓名,总评成绩\n" + "\n".join(
        f"{row['student_no']},{row['student_name']},{score}" for row in rows
    )


def test_grade_csv_import_preview_submit_and_review_snapshot():
    teacher = _headers("tea_li")
    college = _headers("college")
    academic = _headers("jwc")
    with TestClient(app) as client:
        classes = client.get("/api/teaching/operations/tasks", headers=teacher).json()["items"]
        class_id = classes[0]["id"]
        _reset_class(class_id)

        assert client.post(
            f"/api/teaching/classes/{class_id}/grade-submissions", headers=teacher
        ).status_code == 400
        template = client.get(
            f"/api/teaching/classes/{class_id}/grade-template.csv", headers=teacher
        )
        assert template.status_code == 200
        assert template.content.startswith(b"\xef\xbb\xbf")
        assert "学号,姓名,总评成绩" in template.content.decode("utf-8-sig")
        assert client.get(
            f"/api/teaching/classes/{class_id}/grade-template.csv", headers=college
        ).status_code == 403

        roster = client.get(
            f"/api/teaching/classes/{class_id}/grade-roster", headers=teacher
        ).json()["item"]
        rows = roster["items"]
        imported = client.post(
            f"/api/teaching/classes/{class_id}/grade-imports",
            headers=teacher,
            json={"file_name": "验收成绩.csv", "csv_content": _csv(rows)},
        )
        assert imported.status_code == 200
        draft = imported.json()["item"]
        assert draft["status"] == "draft"
        assert draft["detail_count"] == draft["enrolled_count"] == len(rows)
        assert draft["missing_count"] == 0
        assert draft["average_score"] == 88
        assert draft["passed_count"] == len(rows)
        listed = client.get(
            "/api/teaching/grade-submissions", headers=teacher
        ).json()["items"]
        listed_item = next(item for item in listed if item["teaching_class_id"] == class_id)
        assert listed_item["detail_count"] == len(rows)
        assert listed_item["passed_count"] == len(rows)

        submitted = client.post(
            f"/api/teaching/classes/{class_id}/grade-submissions", headers=teacher
        )
        assert submitted.status_code == 200
        submission_id = submitted.json()["item"]["id"]
        college_view = client.get(
            f"/api/teaching/classes/{class_id}/grade-roster", headers=college
        ).json()["item"]
        assert college_view["status"] == "submitted"
        assert [item["final_score"] for item in college_view["items"]] == [88] * len(rows)
        assert client.post(
            f"/api/teaching/classes/{class_id}/grade-imports",
            headers=teacher,
            json={"file_name": "second.csv", "csv_content": _csv(rows, "90")},
        ).status_code == 400

        approved = client.post(
            f"/api/teaching/grade-submissions/{submission_id}/review",
            headers=college,
            json={"action": "approve"},
        )
        assert approved.status_code == 200
        published = client.post(
            f"/api/teaching/grade-submissions/{submission_id}/review",
            headers=academic,
            json={"action": "publish"},
        )
        assert published.status_code == 200
        published_view = client.get(
            f"/api/teaching/classes/{class_id}/grade-roster", headers=academic
        ).json()["item"]
        assert published_view["status"] == "published"
        assert published_view["version_no"] == draft["version_no"]


def test_grade_csv_validation_is_transactional_and_permission_scoped():
    teacher = _headers("tea_li")
    other_teacher = _headers("tea_zhou")
    with TestClient(app) as client:
        class_id = client.get(
            "/api/teaching/operations/tasks", headers=teacher
        ).json()["items"][0]["id"]
        _reset_class(class_id)
        rows = client.get(
            f"/api/teaching/classes/{class_id}/grade-roster", headers=teacher
        ).json()["item"]["items"]

        cases = [
            _csv(rows[:-1]),
            _csv(rows) + f"\n{rows[0]['student_no']},{rows[0]['student_name']},80",
            _csv(rows).replace(",88", ",101", 1),
            _csv(rows) + "\nUNKNOWN,不存在,80",
            "姓名,总评成绩\n测试,80",
        ]
        for content in cases:
            response = client.post(
                f"/api/teaching/classes/{class_id}/grade-imports",
                headers=teacher,
                json={"file_name": "invalid.csv", "csv_content": content},
            )
            assert response.status_code == 400
            with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
                assert conn.execute(
                    "SELECT COUNT(*) FROM grade_submission WHERE teaching_class_id=?",
                    (class_id,),
                ).fetchone()[0] == 0

        assert client.get(
            f"/api/teaching/classes/{class_id}/grade-roster", headers=other_teacher
        ).status_code == 403
        assert client.post(
            f"/api/teaching/classes/{class_id}/grade-imports",
            headers=other_teacher,
            json={"file_name": "grades.csv", "csv_content": _csv(rows)},
        ).status_code == 403
