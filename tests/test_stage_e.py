from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient

from app.core.business_domains import token_for, user_from_token
from app.core import teaching_migrations
from app.main import app


def test_stage_e_teacher_college_and_academic_workflow():
    teacher={"X-Demo-Token":token_for("tea_li")}; college={"X-Demo-Token":token_for("college")}; academic={"X-Demo-Token":token_for("jwc")}
    with TestClient(app) as client:
        assert client.post("/api/teaching/operations/issues/refresh",headers=college).status_code==403
        refreshed=client.post("/api/teaching/operations/issues/refresh",headers=academic)
        assert refreshed.status_code==200
        teacher_tasks=client.get("/api/teaching/operations/tasks",headers=teacher).json()["items"]
        assert teacher_tasks and all(item["teacher_name"]=="李老师" for item in teacher_tasks)
        options=client.get("/api/teaching/operations/filter-options",headers=teacher).json()["item"]
        assert teacher_tasks[0]["year"] in options["years"]
        assert {item["name"] for item in options["colleges"]}=={item["college_name"] for item in teacher_tasks}
        class_id=teacher_tasks[0]["id"]
        keyword=client.get("/api/teaching/operations/tasks",headers=teacher,params={"keyword":teacher_tasks[0]["course_name"]}).json()["items"]
        assert keyword and all(teacher_tasks[0]["course_name"] in item["course_name"] for item in keyword)
        by_year=client.get("/api/teaching/operations/tasks",headers=teacher,params={"year":teacher_tasks[0]["year"]}).json()["items"]
        assert by_year and all(item["year"]==teacher_tasks[0]["year"] for item in by_year)
        assert client.get("/api/teaching/operations/tasks",headers=teacher,params={"semester":"invalid"}).status_code==400
        with sqlite3.connect(teaching_migrations.DB_PATH) as conn:
            submission_ids=[row[0] for row in conn.execute("SELECT id FROM grade_submission WHERE teaching_class_id=?",(class_id,))]
            for submission_id in submission_ids:
                conn.execute("DELETE FROM grade_submission_detail WHERE grade_submission_id=?",(submission_id,))
            conn.execute("DELETE FROM grade_submission WHERE teaching_class_id=?",(class_id,))
            conn.commit()
        roster=client.get(f"/api/teaching/classes/{class_id}/grade-roster",headers=teacher).json()["item"]["items"]
        csv_content="学号,姓名,总评成绩\n"+"\n".join(f"{row['student_no']},{row['student_name']},88" for row in roster)
        imported=client.post(f"/api/teaching/classes/{class_id}/grade-imports",headers=teacher,json={"file_name":"grades.csv","csv_content":csv_content})
        assert imported.status_code==200 and imported.json()["item"]["missing_count"]==0
        submitted=client.post(f"/api/teaching/classes/{class_id}/grade-submissions",headers=teacher)
        assert submitted.status_code==200 and submitted.json()["item"]["status"]=="submitted"
        submitted_tasks=client.get("/api/teaching/operations/tasks",headers=teacher,params={"grade_status":"submitted"}).json()["items"]
        assert any(item["id"]==class_id for item in submitted_tasks)
        submitted_grades=client.get("/api/teaching/grade-submissions",headers=teacher,params={"grade_status":"submitted","year":teacher_tasks[0]["year"]}).json()["items"]
        assert any(item["teaching_class_id"]==class_id for item in submitted_grades)
        submission_id=submitted.json()["item"]["id"]
        assert client.post(f"/api/teaching/grade-submissions/{submission_id}/review",headers=teacher,json={"action":"approve"}).status_code==403
        approved=client.post(f"/api/teaching/grade-submissions/{submission_id}/review",headers=college,json={"action":"approve"})
        assert approved.status_code==200 and approved.json()["item"]["status"]=="approved"
        student={"X-Demo-Token":token_for("stu_zhang")}
        approved_home=client.get("/api/workbench",headers=student).json()
        assert not any(
            item["id"]==class_id
            for section in approved_home["sections"]
            if section["type"]=="published_final_grades"
            for item in section["items"]
        )
        published=client.post(f"/api/teaching/grade-submissions/{submission_id}/review",headers=academic,json={"action":"publish"})
        assert published.status_code==200 and published.json()["item"]["status"]=="published"
        published_home=client.get("/api/workbench",headers=student).json()
        final_grade=next(
            item
            for section in published_home["sections"]
            if section["type"]=="published_final_grades"
            for item in section["items"]
            if item["id"]==class_id
        )
        assert final_grade["meta"]=="88.0 / 100.0"
        student_notices=client.get("/api/notifications",headers=student).json()["items"]
        assert any(item["resource_type"]=="grade_result" and item["resource_id"]==submission_id for item in student_notices)
        summary=client.get("/api/teaching/operations/summary",headers=college)
        assert summary.status_code==200 and summary.json()["item"]["workload"]
        assert all(item["college_id"]==1 for item in summary.json()["item"]["operations"])


def test_stage_e_summary_only_ask_scope_and_frontend():
    academic=user_from_token(token_for("jwc")); college=user_from_token(token_for("college"))
    assert academic.allowed_tables==frozenset({"academic_teaching_operations_summary"})
    assert college.allowed_tables==frozenset({"academic_teaching_operations_summary","college_teacher_workload_summary","college_quality_summary"})
    assert {"teaching_operations","notifications"}.issubset(academic.features)
    assert {"teaching_operations","notifications"}.issubset(college.features)
    root=Path(__file__).parents[1]
    html=(root/"app/static/index.html").read_text(encoding="utf-8")
    script=(root/"app/static/app.js").read_text(encoding="utf-8")
    assert 'id="teaching-operations-view"' in html
    assert 'id="teaching-task-filter-form"' in html and 'id="teaching-task-keyword"' in html
    assert 'id="grade-submission-filter-form"' in html and 'data-stage-e-toggle="grade-submission-panel-body"' in html
    assert 'id="grade-import-modal"' in html and 'id="grade-import-file"' in html
    assert 'id="teaching-task-college"' in html and 'id="grade-submission-year"' in html
    assert "loadTeachingOperations" in script and "data-grade-action" in script and "openGradeRoster" in script
