"""Stage E teaching operations, issues, grade submission and college aggregates."""
from __future__ import annotations

import csv
import io
import math
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


def _notify_published_students(conn, teaching_class_id: int, submission_id: int) -> None:
    course = conn.execute(
        """SELECT c.name
           FROM teaching_class tc JOIN course c ON c.id=tc.course_id
           WHERE tc.id=?""",
        (teaching_class_id,),
    ).fetchone()
    recipients = conn.execute(
        """SELECT DISTINCT au.username
           FROM enrollment e
           JOIN person_identity pi
             ON pi.person_type='student' AND pi.entity_id=e.student_id
            AND pi.status='verified'
           JOIN app_user au ON au.id=pi.user_id AND au.status='active'
           WHERE e.teaching_class_id=?""",
        (teaching_class_id,),
    ).fetchall()
    course_name = course["name"] if course else "课程"
    now = _now()
    conn.executemany(
        """INSERT INTO notification
           (recipient_username,type,title,body,resource_type,resource_id,created_at)
           VALUES (?,'grade_result','课程总评成绩已发布',?,'grade_result',?,?)""",
        [
            (
                recipient["username"],
                f"{course_name}的课程总评成绩已由教务处发布，请在首页查看。",
                submission_id,
                now,
            )
            for recipient in recipients
        ],
    )


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
        rows=conn.execute(f"SELECT ti.*,tc.year academic_year,tc.semester,c.name course_name,col.name college_name,t.name teacher_name FROM teaching_issue ti JOIN teaching_class tc ON tc.id=ti.teaching_class_id JOIN course c ON c.id=tc.course_id JOIN college col ON col.id=c.college_id JOIN teacher t ON t.id=tc.teacher_id WHERE 1=1 {scope} ORDER BY CASE ti.status WHEN 'open' THEN 1 WHEN 'processing' THEN 2 ELSE 3 END,ti.id DESC",params).fetchall()
    return [dict(r) for r in rows]


def assistant_issue_queue(
    ctx: AuthContext,
    *,
    overdue_only: bool = False,
    overdue_hours: int = 72,
    college_id: int | None = None,
    academic_year: int | None = None,
    semester: str | None = None,
) -> list[dict[str, Any]]:
    """Return unresolved teaching issues with a deterministic SLA state."""
    now = datetime.now(timezone.utc)
    items: list[dict[str, Any]] = []
    for raw in list_issues(ctx):
        if college_id is not None and int(raw["college_id"]) != int(college_id):
            continue
        if academic_year is not None and int(raw["academic_year"]) != int(academic_year):
            continue
        if semester is not None and raw["semester"] != semester:
            continue
        if raw["status"] == "resolved":
            continue
        timestamp = raw.get("updated_at") or raw.get("created_at")
        try:
            changed_at = datetime.fromisoformat(str(timestamp))
            if changed_at.tzinfo is None:
                changed_at = changed_at.replace(tzinfo=timezone.utc)
            age_hours = max(0, int((now - changed_at.astimezone(timezone.utc)).total_seconds() // 3600))
        except (TypeError, ValueError):
            age_hours = 0
        is_overdue = age_hours >= overdue_hours
        if overdue_only and not is_overdue:
            continue
        item = dict(raw)
        item["age_hours"] = age_hours
        item["queue_state"] = "已逾期" if is_overdue else ("处理中" if raw["status"] == "processing" else "待处理")
        items.append(item)
    items.sort(key=lambda item: (not item["queue_state"] == "已逾期", -item["age_hours"], item["id"]))
    return items


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
            tc.year,tc.semester,gs.submitted_at,gs.reviewed_at,gs.published_at,
            (SELECT COUNT(*) FROM enrollment e WHERE e.teaching_class_id=tc.id) enrolled_count,
            (SELECT COUNT(*) FROM grade_submission_detail gd
             WHERE gd.grade_submission_id=gs.id AND gd.version_no=gs.version_no) detail_count,
            (SELECT ROUND(AVG(gd.final_score),2) FROM grade_submission_detail gd
             WHERE gd.grade_submission_id=gs.id AND gd.version_no=gs.version_no) average_score,
            (SELECT COUNT(*) FROM grade_submission_detail gd
             WHERE gd.grade_submission_id=gs.id AND gd.version_no=gs.version_no
               AND gd.final_score>=60) passed_count
            FROM teaching_class tc JOIN course c ON c.id=tc.course_id JOIN college col ON col.id=c.college_id
            JOIN teacher t ON t.id=tc.teacher_id
            LEFT JOIN grade_submission gs ON gs.teaching_class_id=tc.id
            WHERE 1=1 {where} ORDER BY tc.id DESC LIMIT 300""",params).fetchall()
    return [dict(r) for r in rows]


def _grade_class_row(conn, teaching_class_id: int):
    return conn.execute(
        """SELECT tc.id teaching_class_id,tc.teacher_id,tc.year,tc.semester,c.college_id,
                  c.course_code,c.name course_name,t.name teacher_name
           FROM teaching_class tc JOIN course c ON c.id=tc.course_id
           JOIN teacher t ON t.id=tc.teacher_id WHERE tc.id=?""",
        (teaching_class_id,),
    ).fetchone()


def _require_grade_class_access(ctx: AuthContext, conn, teaching_class_id: int, *, teacher_only: bool = False):
    row = _grade_class_row(conn, teaching_class_id)
    if not row:
        raise ValueError("课程不存在")
    if ctx.role == "teacher":
        if row["teacher_id"] != ctx.row_scope.get("teacher_id"):
            forbidden()
    elif not teacher_only and ctx.role == "college_manager":
        if row["college_id"] != ctx.row_scope.get("college_id"):
            forbidden()
    elif not teacher_only and ctx.role == "academic_office":
        pass
    else:
        forbidden()
    return row


def grade_roster(ctx: AuthContext, teaching_class_id: int) -> dict[str, Any]:
    with connect() as conn:
        class_row = _require_grade_class_access(ctx, conn, teaching_class_id)
        submission = conn.execute(
            "SELECT * FROM grade_submission WHERE teaching_class_id=?",
            (teaching_class_id,),
        ).fetchone()
        version_no = int(submission["version_no"]) if submission else 0
        rows = conn.execute(
            """SELECT e.id enrollment_id,s.student_no,s.name student_name,gd.final_score
               FROM enrollment e JOIN student s ON s.id=e.student_id
               LEFT JOIN grade_submission_detail gd
                 ON gd.enrollment_id=e.id AND gd.grade_submission_id=?
                AND gd.version_no=?
               WHERE e.teaching_class_id=? ORDER BY s.student_no""",
            (int(submission["id"]) if submission else 0, version_no, teaching_class_id),
        ).fetchall()
    items = [dict(row) for row in rows]
    scores = [float(row["final_score"]) for row in rows if row["final_score"] is not None]
    return {
        "teaching_class_id": teaching_class_id,
        "course_code": class_row["course_code"],
        "course_name": class_row["course_name"],
        "teacher_name": class_row["teacher_name"],
        "year": class_row["year"],
        "semester": class_row["semester"],
        "submission_id": int(submission["id"]) if submission else 0,
        "version_no": version_no,
        "status": submission["status"] if submission else "not_submitted",
        "returned_reason": submission["returned_reason"] if submission else "",
        "enrolled_count": len(items),
        "detail_count": len(scores),
        "missing_count": len(items) - len(scores),
        "average_score": round(sum(scores) / len(scores), 2) if scores else None,
        "passed_count": sum(score >= 60 for score in scores),
        "items": items,
    }


def grade_template_csv(ctx: AuthContext, teaching_class_id: int) -> tuple[str, str]:
    require_teacher_of_class(ctx, teaching_class_id)
    with connect() as conn:
        class_row = _grade_class_row(conn, teaching_class_id)
        rows = conn.execute(
            """SELECT s.student_no,s.name student_name,sc.final_score
               FROM enrollment e JOIN student s ON s.id=e.student_id
               LEFT JOIN score sc ON sc.enrollment_id=e.id
               WHERE e.teaching_class_id=? ORDER BY s.student_no""",
            (teaching_class_id,),
        ).fetchall()
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["学号", "姓名", "总评成绩"])
    for row in rows:
        writer.writerow([row["student_no"], row["student_name"], row["final_score"] if row["final_score"] is not None else ""])
    safe_code = "".join(ch for ch in str(class_row["course_code"]) if ch.isalnum() or ch in "-_") or str(teaching_class_id)
    return f"\ufeff{output.getvalue()}", f"{safe_code}-总评成绩导入模板.csv"


def import_grade_csv(ctx: AuthContext, teaching_class_id: int, csv_content: str, file_name: str = "") -> dict[str, Any]:
    require_teacher_of_class(ctx, teaching_class_id)
    if "\x00" in csv_content:
        raise ValueError("成绩文件包含无效字符")
    try:
        reader = csv.DictReader(io.StringIO(csv_content.lstrip("\ufeff"), newline=""))
        raw_headers = reader.fieldnames or []
    except csv.Error as exc:
        raise ValueError("成绩文件无法解析，请使用 CSV 格式") from exc
    headers = {str(header).strip(): header for header in raw_headers if header is not None}
    student_no_header = next((headers[key] for key in ("学号", "student_no") if key in headers), None)
    student_name_header = next((headers[key] for key in ("姓名", "student_name") if key in headers), None)
    score_header = next((headers[key] for key in ("总评成绩", "final_score") if key in headers), None)
    if not student_no_header or not score_header:
        raise ValueError("CSV 必须包含“学号”和“总评成绩”列")

    parsed: list[tuple[int, str, str, float]] = []
    seen: set[str] = set()
    try:
        for row_no, row in enumerate(reader, start=2):
            if not any(str(value or "").strip() for value in row.values()):
                continue
            student_no = str(row.get(student_no_header) or "").strip()
            student_name = str(row.get(student_name_header) or "").strip() if student_name_header else ""
            score_text = str(row.get(score_header) or "").strip()
            if not student_no:
                raise ValueError(f"第 {row_no} 行学号不能为空")
            if student_no in seen:
                raise ValueError(f"第 {row_no} 行学号 {student_no} 重复")
            seen.add(student_no)
            if not score_text:
                raise ValueError(f"第 {row_no} 行总评成绩不能为空")
            try:
                score = float(score_text)
            except ValueError as exc:
                raise ValueError(f"第 {row_no} 行总评成绩不是有效数字") from exc
            if not math.isfinite(score) or score < 0 or score > 100:
                raise ValueError(f"第 {row_no} 行总评成绩必须在 0 到 100 之间")
            if round(score, 2) != score:
                raise ValueError(f"第 {row_no} 行总评成绩最多保留两位小数")
            parsed.append((row_no, student_no, student_name, score))
    except csv.Error as exc:
        raise ValueError("成绩文件存在格式错误") from exc

    with connect() as conn:
        roster_rows = conn.execute(
            """SELECT e.id enrollment_id,s.student_no,s.name student_name
               FROM enrollment e JOIN student s ON s.id=e.student_id
               WHERE e.teaching_class_id=? ORDER BY s.student_no""",
            (teaching_class_id,),
        ).fetchall()
        roster = {row["student_no"]: row for row in roster_rows}
        unknown = sorted(student_no for _, student_no, _, _ in parsed if student_no not in roster)
        missing = sorted(set(roster) - seen)
        if unknown:
            raise ValueError(f"存在不属于本课程的学号：{', '.join(unknown[:5])}")
        if missing:
            raise ValueError(f"成绩名单不完整，缺少 {len(missing)} 人：{', '.join(missing[:5])}")
        if not roster:
            raise ValueError("课程没有选课学生，不能导入成绩")
        if len(parsed) != len(roster):
            raise ValueError("成绩行数与课程选课名单不一致")
        for row_no, student_no, student_name, _score in parsed:
            if student_name and student_name != roster[student_no]["student_name"]:
                raise ValueError(f"第 {row_no} 行学号与姓名不匹配：{student_no}")

        submission = conn.execute(
            "SELECT * FROM grade_submission WHERE teaching_class_id=?",
            (teaching_class_id,),
        ).fetchone()
        if submission and submission["status"] not in {"draft", "returned"}:
            raise ValueError("当前成绩状态不允许重新导入")
        now = _now()
        if submission:
            version_no = int(submission["version_no"]) + 1
            submission_id = int(submission["id"])
            conn.execute(
                """UPDATE grade_submission
                   SET version_no=?,status='draft',returned_reason='',submitted_at=NULL,
                       reviewed_by_user_id=NULL,reviewed_at=NULL,published_at=NULL,updated_at=?
                   WHERE id=?""",
                (version_no, now, submission_id),
            )
        else:
            version_no = 1
            cursor = conn.execute(
                """INSERT INTO grade_submission
                   (teaching_class_id,submitter_user_id,version_no,status,updated_at)
                   VALUES (?,?,?,'draft',?)""",
                (teaching_class_id, ctx.user_id, version_no, now),
            )
            submission_id = int(cursor.lastrowid)
        conn.executemany(
            """INSERT INTO grade_submission_detail
               (grade_submission_id,version_no,enrollment_id,student_no_snapshot,
                student_name_snapshot,final_score,import_row_no,created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            [
                (
                    submission_id,
                    version_no,
                    int(roster[student_no]["enrollment_id"]),
                    student_no,
                    roster[student_no]["student_name"],
                    score,
                    row_no,
                    now,
                )
                for row_no, student_no, _student_name, score in parsed
            ],
        )
        conn.execute(
            """INSERT INTO audit_log
               (actor_user,actor_role,resource_type,resource_id,action,before_state,after_state,created_at)
               VALUES (?,?,'grade_submission',?,'import_grade_csv',?,?,?)""",
            (
                ctx.username,
                ctx.role,
                submission_id,
                submission["status"] if submission else "not_submitted",
                f"draft:v{version_no}:{len(parsed)}:{file_name[:120]}",
                now,
            ),
        )
        conn.commit()
    refresh_summaries()
    return grade_roster(ctx, teaching_class_id)


def submit_grades(ctx: AuthContext, teaching_class_id: int) -> dict[str, Any]:
    require_teacher_of_class(ctx,teaching_class_id)
    with connect() as conn:
        row=conn.execute("SELECT * FROM grade_submission WHERE teaching_class_id=?",(teaching_class_id,)).fetchone(); now=_now()
        if not row or row["status"] != "draft":
            raise ValueError("请先导入并确认完整的总评成绩")
        enrolled_count = conn.execute(
            "SELECT COUNT(*) FROM enrollment WHERE teaching_class_id=?",
            (teaching_class_id,),
        ).fetchone()[0]
        detail_count = conn.execute(
            """SELECT COUNT(*) FROM grade_submission_detail
               WHERE grade_submission_id=? AND version_no=?""",
            (row["id"], row["version_no"]),
        ).fetchone()[0]
        if not enrolled_count or detail_count != enrolled_count:
            raise ValueError("成绩名单不完整，不能提交审批")
        conn.execute(
            "UPDATE grade_submission SET status='submitted',returned_reason='',submitted_at=?,updated_at=? WHERE id=?",
            (now,now,row["id"]),
        )
        sid=int(row["id"])
        conn.execute(
            """INSERT INTO audit_log
               (actor_user,actor_role,resource_type,resource_id,action,before_state,after_state,created_at)
               VALUES (?,?,'grade_submission',?,'submit_grades','draft','submitted',?)""",
            (ctx.username,ctx.role,sid,now),
        )
        conn.commit()
    refresh_summaries(); return {"id":sid,"status":"submitted","version_no":int(row["version_no"]),"detail_count":detail_count}


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
        _notify(conn,_teacher_username(conn,row["teaching_class_id"]),"成绩提交状态更新",status,submission_id)
        if status == "published":
            _notify_published_students(conn, int(row["teaching_class_id"]), submission_id)
        conn.commit()
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
