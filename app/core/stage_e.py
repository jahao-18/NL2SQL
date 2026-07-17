"""Stage E teaching operations, issues, grade submission and college aggregates."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.authorization import connect, forbidden, require_teacher_of_class
from app.core.business_domains import AuthContext


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _scope(ctx: AuthContext) -> tuple[str, tuple[Any, ...]]:
    if ctx.role == "college_manager" and ctx.row_scope.get("college_id"):
        return " AND c.college_id = ?", (int(ctx.row_scope["college_id"]),)
    if ctx.role == "academic_office":
        return "", ()
    if ctx.role == "teacher" and ctx.row_scope.get("teacher_id"):
        return " AND tc.teacher_id = ?", (int(ctx.row_scope["teacher_id"]),)
    forbidden()


def _teacher_username(conn, teaching_class_id: int) -> str | None:
    row = conn.execute("SELECT au.username FROM teaching_class tc JOIN staff st ON st.teacher_id=tc.teacher_id JOIN person_identity pi ON pi.person_type='staff' AND pi.entity_id=st.id AND pi.status='verified' JOIN app_user au ON au.id=pi.user_id WHERE tc.id=? LIMIT 1", (teaching_class_id,)).fetchone()
    return row["username"] if row else None


def _notify(conn, username: str | None, title: str, body: str, resource_id: int) -> None:
    if username:
        conn.execute("INSERT INTO notification(recipient_username,type,title,body,resource_type,resource_id,created_at) VALUES (?,'grade_submission',?,?, 'grade_submission',?,?)", (username, title, body, resource_id, _now()))


def refresh_summaries() -> None:
    with connect() as conn:
        now = _now()
        conn.execute("DELETE FROM academic_teaching_operations_summary")
        conn.execute("""INSERT INTO academic_teaching_operations_summary
            SELECT tc.id,c.college_id,col.name,c.name,t.name,tc.year,tc.semester,COALESCE(tc.classroom,''),tc.capacity,
                   COUNT(DISTINCT e.student_id),COUNT(DISTINCT CASE WHEN ti.status<>'resolved' THEN ti.id END),COALESCE(gs.status,'not_submitted'),?
            FROM teaching_class tc JOIN course c ON c.id=tc.course_id JOIN college col ON col.id=c.college_id
            JOIN teacher t ON t.id=tc.teacher_id LEFT JOIN enrollment e ON e.teaching_class_id=tc.id
            LEFT JOIN teaching_issue ti ON ti.teaching_class_id=tc.id LEFT JOIN grade_submission gs ON gs.teaching_class_id=tc.id
            GROUP BY tc.id""", (now,))
        conn.execute("DELETE FROM college_teacher_workload_summary")
        conn.execute("""INSERT INTO college_teacher_workload_summary
            SELECT c.college_id,t.name,COUNT(DISTINCT tc.id),COUNT(DISTINCT e.id),?
            FROM teaching_class tc JOIN course c ON c.id=tc.course_id JOIN teacher t ON t.id=tc.teacher_id
            LEFT JOIN enrollment e ON e.teaching_class_id=tc.id GROUP BY c.college_id,t.name""", (now,))
        conn.execute("DELETE FROM college_quality_summary")
        conn.execute("""INSERT INTO college_quality_summary
            SELECT c.college_id,c.name,COUNT(DISTINCT tc.id),COUNT(DISTINCT e.id),COUNT(DISTINCT s.id),
                   CASE WHEN COUNT(DISTINCT s.id)>=5 THEN ROUND(AVG(s.final_score),2) END,
                   CASE WHEN COUNT(DISTINCT s.id)>=5 THEN ROUND(100.0*SUM(CASE WHEN s.passed=1 THEN 1 ELSE 0 END)/COUNT(s.id),2) END,?
            FROM course c JOIN teaching_class tc ON tc.course_id=c.id LEFT JOIN enrollment e ON e.teaching_class_id=tc.id
            LEFT JOIN score s ON s.enrollment_id=e.id GROUP BY c.college_id,c.name""", (now,))
        conn.commit()


def _filtered_scope(
    ctx: AuthContext,
    keyword: str = "",
    year: int | None = None,
    semester: str = "",
    grade_status: str = "",
    college_id: int | None = None,
) -> tuple[str, tuple[Any, ...]]:
    where, scope_params = _scope(ctx)
    params: list[Any] = list(scope_params)
    keyword = keyword.strip()
    if keyword:
        where += " AND (c.name LIKE ? OR t.name LIKE ? OR col.name LIKE ?)"
        pattern = f"%{keyword}%"
        params.extend((pattern, pattern, pattern))
    if year is not None:
        where += " AND tc.year = ?"
        params.append(year)
    if semester:
        if semester not in {"spring", "fall"}:
            raise ValueError("学期筛选值不正确")
        where += " AND tc.semester = ?"
        params.append(semester)
    if grade_status:
        if grade_status not in {"not_submitted", "draft", "submitted", "returned", "approved", "published"}:
            raise ValueError("成绩状态筛选值不正确")
        where += " AND COALESCE(gs.status, 'not_submitted') = ?"
        params.append(grade_status)
    if college_id is not None:
        where += " AND c.college_id = ?"
        params.append(college_id)
    return where, tuple(params)


def operation_filter_options(ctx: AuthContext) -> dict[str, list[Any]]:
    where, params = _scope(ctx)
    with connect() as conn:
        years = [row["year"] for row in conn.execute(f"""SELECT DISTINCT tc.year
            FROM teaching_class tc JOIN course c ON c.id=tc.course_id JOIN college col ON col.id=c.college_id
            JOIN teacher t ON t.id=tc.teacher_id WHERE 1=1 {where} ORDER BY tc.year DESC""", params).fetchall()]
        colleges = [dict(row) for row in conn.execute(f"""SELECT DISTINCT col.id,col.name
            FROM teaching_class tc JOIN course c ON c.id=tc.course_id JOIN college col ON col.id=c.college_id
            JOIN teacher t ON t.id=tc.teacher_id WHERE 1=1 {where} ORDER BY col.name""", params).fetchall()]
    return {"years": years, "colleges": colleges}


def task_ledger(ctx: AuthContext, keyword: str = "", year: int | None = None, semester: str = "", grade_status: str = "", college_id: int | None = None) -> list[dict[str, Any]]:
    where, params = _filtered_scope(ctx, keyword, year, semester, grade_status, college_id)
    with connect() as conn:
        rows = conn.execute(f"""SELECT tc.id,c.college_id,col.name AS college_name,c.name AS course_name,t.name AS teacher_name,
            tc.year,tc.semester,tc.classroom,tc.capacity,COUNT(e.id) AS enrolled_count,COALESCE(gs.status,'not_submitted') AS grade_status
            FROM teaching_class tc JOIN course c ON c.id=tc.course_id JOIN college col ON col.id=c.college_id JOIN teacher t ON t.id=tc.teacher_id
            LEFT JOIN enrollment e ON e.teaching_class_id=tc.id LEFT JOIN grade_submission gs ON gs.teaching_class_id=tc.id
            WHERE 1=1 {where} GROUP BY tc.id ORDER BY tc.year DESC,tc.id DESC LIMIT 300""", params).fetchall()
    return [dict(row) for row in rows]


def refresh_issues(ctx: AuthContext) -> dict[str, int]:
    if ctx.role != "academic_office": forbidden()
    created = 0
    with connect() as conn:
        rows = conn.execute("""SELECT tc.id,c.college_id,tc.capacity,COALESCE(tc.classroom,'') classroom,COUNT(e.id) enrolled
            FROM teaching_class tc JOIN course c ON c.id=tc.course_id LEFT JOIN enrollment e ON e.teaching_class_id=tc.id GROUP BY tc.id""").fetchall()
        now = _now()
        for row in rows:
            rules = []
            if not row["classroom"].strip(): rules.append(("missing_classroom", "未安排教室"))
            if row["enrolled"] > row["capacity"]: rules.append(("over_capacity", f"选课 {row['enrolled']} 人，超过容量 {row['capacity']}"))
            if 0 < row["enrolled"] < 5: rules.append(("low_enrollment", f"选课仅 {row['enrolled']} 人"))
            for issue_type, evidence in rules:
                key=f"{issue_type}:{row['id']}"
                cur=conn.execute("INSERT OR IGNORE INTO teaching_issue(issue_key,issue_type,teaching_class_id,college_id,evidence,status,created_at,updated_at) VALUES (?,?,?,?,?,'open',?,?)", (key,issue_type,row["id"],row["college_id"],evidence,now,now))
                created += cur.rowcount
        conn.commit()
    refresh_summaries()
    return {"created_count": created}


def list_issues(ctx: AuthContext) -> list[dict[str, Any]]:
    if ctx.role not in {"academic_office","college_manager"}: forbidden()
    scope=""; params=()
    if ctx.role=="college_manager": scope=" AND ti.college_id=?"; params=(ctx.row_scope["college_id"],)
    with connect() as conn:
        rows=conn.execute(f"SELECT ti.*,c.name course_name,t.name teacher_name FROM teaching_issue ti JOIN teaching_class tc ON tc.id=ti.teaching_class_id JOIN course c ON c.id=tc.course_id JOIN teacher t ON t.id=tc.teacher_id WHERE 1=1 {scope} ORDER BY CASE ti.status WHEN 'open' THEN 1 WHEN 'processing' THEN 2 ELSE 3 END,ti.id DESC",params).fetchall()
    return [dict(r) for r in rows]


def update_issue(ctx: AuthContext, issue_id: int, status: str, resolution: str) -> dict[str, Any]:
    if ctx.role not in {"academic_office","college_manager"} or status not in {"open","processing","resolved"}: forbidden()
    if status=="resolved" and not resolution.strip(): raise ValueError("解决异常必须填写处理说明")
    with connect() as conn:
        row=conn.execute("SELECT * FROM teaching_issue WHERE id=?",(issue_id,)).fetchone()
        if not row: raise ValueError("教学异常不存在")
        if ctx.role=="college_manager" and row["college_id"]!=ctx.row_scope.get("college_id"): forbidden()
        now=_now(); conn.execute("UPDATE teaching_issue SET status=?,resolution=?,updated_at=?,resolved_at=? WHERE id=?",(status,resolution.strip(),now,now if status=="resolved" else None,issue_id))
        conn.execute("INSERT INTO audit_log(actor_user,actor_role,resource_type,resource_id,action,before_state,after_state,created_at) VALUES (?,?, 'teaching_issue',?,'update_issue',?,?,?)",(ctx.username,ctx.role,issue_id,row["status"],status,now)); conn.commit()
    refresh_summaries(); return {"id":issue_id,"status":status}


def list_grade_submissions(ctx: AuthContext, keyword: str = "", year: int | None = None, semester: str = "", grade_status: str = "", college_id: int | None = None) -> list[dict[str, Any]]:
    where, params = _filtered_scope(ctx, keyword, year, semester, grade_status, college_id)
    with connect() as conn:
        rows=conn.execute(f"""SELECT tc.id teaching_class_id,c.name course_name,col.name college_name,t.name teacher_name,
            COALESCE(gs.id,0) id,COALESCE(gs.version_no,0) version_no,COALESCE(gs.status,'not_submitted') status,COALESCE(gs.returned_reason,'') returned_reason,
            tc.year,tc.semester,gs.submitted_at,gs.reviewed_at,gs.published_at FROM teaching_class tc JOIN course c ON c.id=tc.course_id JOIN college col ON col.id=c.college_id
            JOIN teacher t ON t.id=tc.teacher_id LEFT JOIN grade_submission gs ON gs.teaching_class_id=tc.id WHERE 1=1 {where} ORDER BY tc.id DESC LIMIT 300""",params).fetchall()
    return [dict(r) for r in rows]


def submit_grades(ctx: AuthContext, teaching_class_id: int) -> dict[str, Any]:
    require_teacher_of_class(ctx,teaching_class_id)
    with connect() as conn:
        row=conn.execute("SELECT * FROM grade_submission WHERE teaching_class_id=?",(teaching_class_id,)).fetchone(); now=_now()
        if row and row["status"] not in {"draft","returned"}: raise ValueError("当前成绩提交状态不能再次提交")
        if row:
            conn.execute("UPDATE grade_submission SET version_no=version_no+1,status='submitted',returned_reason='',submitted_at=?,updated_at=? WHERE id=?",(now,now,row["id"])); sid=row["id"]
        else:
            cur=conn.execute("INSERT INTO grade_submission(teaching_class_id,submitter_user_id,status,submitted_at,updated_at) VALUES (?,?,'submitted',?,?)",(teaching_class_id,ctx.user_id,now,now));sid=int(cur.lastrowid)
        conn.commit()
    refresh_summaries(); return {"id":sid,"status":"submitted"}


def review_grades(ctx: AuthContext, submission_id: int, action: str, reason: str="") -> dict[str, Any]:
    if ctx.role not in {"college_manager","academic_office"}: forbidden()
    with connect() as conn:
        row=conn.execute("SELECT gs.*,c.college_id FROM grade_submission gs JOIN teaching_class tc ON tc.id=gs.teaching_class_id JOIN course c ON c.id=tc.course_id WHERE gs.id=?",(submission_id,)).fetchone()
        if not row: raise ValueError("成绩提交不存在")
        if ctx.role=="college_manager" and row["college_id"]!=ctx.row_scope.get("college_id"): forbidden()
        if action in {"approve","return"}:
            if row["status"]!="submitted": raise ValueError("只有待审批成绩可以处理")
            status="approved" if action=="approve" else "returned"
            if status=="returned" and not reason.strip(): raise ValueError("退回必须填写原因")
        elif action=="publish" and ctx.role=="academic_office":
            if row["status"]!="approved": raise ValueError("只有已审批成绩可以发布")
            status="published"
        else: forbidden()
        now=_now();conn.execute("UPDATE grade_submission SET status=?,returned_reason=?,reviewed_by_user_id=?,reviewed_at=?,published_at=?,updated_at=? WHERE id=?",(status,reason.strip() if status=="returned" else "",ctx.user_id,now,now if status=="published" else None,now,submission_id))
        _notify(conn,_teacher_username(conn,row["teaching_class_id"]),"成绩提交状态更新",status,submission_id);conn.commit()
    refresh_summaries();return {"id":submission_id,"status":status}


def operations_summary(ctx: AuthContext) -> dict[str, Any]:
    if ctx.role not in {"academic_office","college_manager"}: forbidden()
    refresh_summaries(); scope="";params=()
    if ctx.role=="college_manager":scope=" WHERE college_id=?";params=(ctx.row_scope["college_id"],)
    with connect() as conn:
        operations=[dict(r) for r in conn.execute(f"SELECT * FROM academic_teaching_operations_summary{scope} ORDER BY enrolled_count DESC LIMIT 100",params).fetchall()]
        workload=[];quality=[]
        if ctx.role=="college_manager":
            workload=[dict(r) for r in conn.execute("SELECT * FROM college_teacher_workload_summary WHERE college_id=? ORDER BY class_count DESC",params).fetchall()]
            quality=[dict(r) for r in conn.execute("SELECT * FROM college_quality_summary WHERE college_id=? ORDER BY course_name",params).fetchall()]
    return {"operations":operations,"workload":workload,"quality":quality}
