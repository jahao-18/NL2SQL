"""Teaching dashboard metrics.

These queries are deterministic operational metrics, not NL2SQL output. Keeping
them here makes the dashboard fast and stable while the assistant remains LLM
driven.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.core.data_sources import get_engine, get_source


def _rows(conn, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [dict(row._mapping) for row in conn.execute(text(sql), params or {}).all()]


def _one(conn, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    row = conn.execute(text(sql), params or {}).first()
    return dict(row._mapping) if row else {}


COURSE_TYPE_LABELS = {
    "required": "必修",
    "general": "通识",
    "elective": "选修",
}

COURSE_TYPE_VALUES = {
    "required": "required",
    "general": "general",
    "elective": "elective",
    "必修": "required",
    "通识": "general",
    "实践": "general",
    "选修": "elective",
}


def _normalize_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    raw = filters or {}
    result: dict[str, Any] = {
        "term": str(raw.get("term") or "").strip(),
        "college": str(raw.get("college") or "").strip(),
        "major": str(raw.get("major") or "").strip(),
        "course_type": str(raw.get("course_type") or raw.get("courseType") or "").strip(),
    }
    if result["term"] and "-" in result["term"]:
        year, semester = result["term"].split("-", 1)
        if year.isdigit():
            result["year"] = int(year)
            result["semester"] = semester
    if result["course_type"]:
        result["course_type"] = COURSE_TYPE_VALUES.get(result["course_type"], result["course_type"])
    return result


def _filter_options(conn) -> dict[str, Any]:
    terms = _rows(
        conn,
        """
        SELECT CAST(year AS TEXT) || '-' || semester AS value,
               CAST(year AS TEXT) || CASE semester WHEN 'spring' THEN ' 春季学期' WHEN 'autumn' THEN ' 秋季学期' ELSE ' ' || semester END AS label
        FROM academic_warning
        GROUP BY year, semester
        HAVING COUNT(*) > 0
        ORDER BY year DESC, semester DESC
        """,
    )
    course_types = _rows(
        conn,
        "SELECT course_type AS value FROM course WHERE course_type IS NOT NULL GROUP BY course_type ORDER BY course_type",
    )
    for item in course_types:
        item["label"] = COURSE_TYPE_LABELS.get(item["value"], item["value"])
    return {
        "terms": terms,
        "colleges": [r["name"] for r in _rows(conn, "SELECT name FROM college ORDER BY id")],
        "majors": _rows(
            conn,
            """
            SELECT m.name AS value, m.name AS label, c.name AS college
            FROM major m
            JOIN college c ON m.college_id = c.id
            ORDER BY c.id, m.id
            """,
        ),
        "course_types": course_types,
    }


def _apply_filters(
    filters: dict[str, Any],
    params: dict[str, Any],
    *,
    student_alias: str | None = None,
    course_alias: str | None = None,
    class_alias: str | None = None,
    warning_alias: str | None = None,
    college_scope: str = "student",
) -> str:
    clauses: list[str] = []
    if filters.get("year") is not None and filters.get("semester"):
        params["year"] = filters["year"]
        params["semester"] = filters["semester"]
        if class_alias:
            clauses.append(f"{class_alias}.year = :year AND {class_alias}.semester = :semester")
        elif warning_alias:
            clauses.append(f"{warning_alias}.year = :year AND {warning_alias}.semester = :semester")
    if filters.get("college"):
        params["college_name"] = filters["college"]
        if college_scope == "course" and course_alias:
            clauses.append(f"{course_alias}.college_id IN (SELECT id FROM college WHERE name = :college_name)")
        elif student_alias:
            clauses.append(f"{student_alias}.college_id IN (SELECT id FROM college WHERE name = :college_name)")
        elif course_alias:
            clauses.append(f"{course_alias}.college_id IN (SELECT id FROM college WHERE name = :college_name)")
    if filters.get("major") and student_alias:
        params["major_name"] = filters["major"]
        clauses.append(f"{student_alias}.major_id IN (SELECT id FROM major WHERE name = :major_name)")
    if filters.get("course_type") and course_alias:
        params["course_type"] = filters["course_type"]
        clauses.append(f"{course_alias}.course_type = :course_type")
    elif filters.get("course_type") and student_alias:
        params["course_type"] = filters["course_type"]
        clauses.append(
            f"""
            EXISTS (
              SELECT 1
              FROM enrollment f_e
              JOIN teaching_class f_tc ON f_e.teaching_class_id = f_tc.id
              JOIN course f_c ON f_tc.course_id = f_c.id
              WHERE f_e.student_id = {student_alias}.id AND f_c.course_type = :course_type
            )
            """
        )
    return (" AND " + " AND ".join(clauses)) if clauses else ""


def teaching_dashboard(
    source_name: str = "teaching",
    allowed_tables: set[str] | frozenset[str] | None = None,
    row_scope: dict[str, Any] | None = None,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = get_source(source_name)
    if source.name != "teaching":
        raise ValueError("teaching dashboard only supports the teaching data source")
    allowed = set(allowed_tables or [])
    unrestricted = not allowed

    def can(*tables: str) -> bool:
        return unrestricted or set(tables).issubset(allowed)

    engine = get_engine(source)
    row_scope = row_scope or {}
    filters = _normalize_filters(filters)

    if row_scope.get("student_id"):
        student_id = row_scope["student_id"]
        params = {"student_id": student_id}
        with engine.connect() as conn:
            cards: dict[str, Any] = {}
            if can("course", "teaching_class", "enrollment"):
                cards["course_count"] = _one(
                    conn,
                    """
                    SELECT COUNT(DISTINCT c.id) AS value
                    FROM enrollment e
                    JOIN teaching_class tc ON e.teaching_class_id = tc.id
                    JOIN course c ON tc.course_id = c.id
                    WHERE e.student_id = :student_id
                    """,
                    params,
                ).get("value")
                cards["current_classes"] = _one(
                    conn,
                    """
                    SELECT COUNT(DISTINCT tc.id) AS value
                    FROM enrollment e
                    JOIN teaching_class tc ON e.teaching_class_id = tc.id
                    WHERE e.student_id = :student_id AND tc.year = 2025 AND tc.semester = 'spring'
                    """,
                    params,
                ).get("value")
                cards["current_enrollments"] = cards["current_classes"]
            if can("score", "enrollment"):
                cards.update(_one(
                    conn,
                    """
                    SELECT
                      ROUND(AVG(sc.final_score), 2) AS avg_score,
                      ROUND(AVG(CASE WHEN sc.final_score >= 60 THEN 1.0 ELSE 0.0 END) * 100, 2) AS pass_rate,
                      ROUND(AVG(CASE WHEN sc.final_score < 60 THEN 1.0 ELSE 0.0 END) * 100, 2) AS fail_rate
                    FROM score sc
                    JOIN enrollment e ON sc.enrollment_id = e.id
                    WHERE e.student_id = :student_id
                    """,
                    params,
                ))
            if can("assignment_submission"):
                cards["assignment_submit_rate"] = _one(
                    conn,
                    """
                    SELECT ROUND(AVG(CASE WHEN status <> 'missing' THEN 1.0 ELSE 0.0 END) * 100, 2) AS value
                    FROM assignment_submission
                    WHERE student_id = :student_id
                    """,
                    params,
                ).get("value")
            if can("attendance"):
                cards["attendance_rate"] = _one(
                    conn,
                    """
                    SELECT ROUND(AVG(CASE WHEN status = 'present' THEN 1.0 ELSE 0.0 END) * 100, 2) AS value
                    FROM attendance
                    WHERE student_id = :student_id
                    """,
                    params,
                ).get("value")
            if can("academic_warning"):
                cards["open_warnings"] = _one(
                    conn,
                    "SELECT COUNT(*) AS value FROM academic_warning WHERE resolved = 0 AND student_id = :student_id",
                    params,
                ).get("value")
            if can("learning_activity"):
                cards["activity_records"] = _one(
                    conn,
                    "SELECT COUNT(*) AS value FROM learning_activity WHERE student_id = :student_id",
                    params,
                ).get("value")

            score_distribution = _rows(
                conn,
                """
                SELECT bucket AS label, COUNT(*) AS value
                FROM (
                  SELECT CASE
                    WHEN sc.final_score < 60 THEN '0-59'
                    WHEN sc.final_score < 70 THEN '60-69'
                    WHEN sc.final_score < 80 THEN '70-79'
                    WHEN sc.final_score < 90 THEN '80-89'
                    ELSE '90-100'
                  END AS bucket,
                  CASE
                    WHEN sc.final_score < 60 THEN 1
                    WHEN sc.final_score < 70 THEN 2
                    WHEN sc.final_score < 80 THEN 3
                    WHEN sc.final_score < 90 THEN 4
                    ELSE 5
                  END AS bucket_order
                  FROM score sc
                  JOIN enrollment e ON sc.enrollment_id = e.id
                  WHERE e.student_id = :student_id
                )
                GROUP BY bucket, bucket_order
                ORDER BY bucket_order
                """,
                params,
            ) if can("score", "enrollment") else []
            low_score_courses = _rows(
                conn,
                """
                SELECT c.name AS course_name,
                       ROUND(sc.final_score, 2) AS avg_score,
                       1 AS enrollment_count
                FROM score sc
                JOIN enrollment e ON sc.enrollment_id = e.id
                JOIN teaching_class tc ON e.teaching_class_id = tc.id
                JOIN course c ON tc.course_id = c.id
                WHERE e.student_id = :student_id
                ORDER BY sc.final_score ASC
                LIMIT 8
                """,
                params,
            ) if can("score", "enrollment", "teaching_class", "course") else []
            attendance_risk_courses = _rows(
                conn,
                """
                SELECT c.name AS course_name,
                       ROUND(AVG(CASE WHEN a.status = 'absent' THEN 1.0 ELSE 0.0 END) * 100, 2) AS absent_rate,
                       COUNT(a.id) AS attendance_count
                FROM attendance a
                JOIN teaching_class tc ON a.teaching_class_id = tc.id
                JOIN course c ON tc.course_id = c.id
                WHERE a.student_id = :student_id
                GROUP BY c.id, c.name
                ORDER BY absent_rate DESC, attendance_count DESC
                LIMIT 8
                """,
                params,
            ) if can("attendance", "teaching_class", "course") else []
        return {
            "source": source.name,
            "source_label": source.label,
            "cards": cards,
            "students_by_college": [],
            "score_distribution": score_distribution,
            "low_score_courses": low_score_courses,
            "fail_rate_courses": low_score_courses,
            "teacher_workload": [],
            "college_quality": [],
            "attendance_risk_courses": attendance_risk_courses,
            "warning_by_major": [],
        }

    if row_scope.get("teacher_id"):
        teacher_id = row_scope["teacher_id"]
        params = {"teacher_id": teacher_id}
        with engine.connect() as conn:
            cards = {}
            if can("course", "teaching_class"):
                cards["course_count"] = _one(
                    conn,
                    """
                    SELECT COUNT(DISTINCT c.id) AS value
                    FROM teaching_class tc
                    JOIN course c ON tc.course_id = c.id
                    WHERE tc.teacher_id = :teacher_id
                    """,
                    params,
                ).get("value")
                cards["current_classes"] = _one(
                    conn,
                    """
                    SELECT COUNT(*) AS value FROM teaching_class
                    WHERE teacher_id = :teacher_id AND year = 2025 AND semester = 'spring'
                    """,
                    params,
                ).get("value")
            if can("enrollment", "teaching_class"):
                cards["current_enrollments"] = _one(
                    conn,
                    """
                    SELECT COUNT(e.id) AS value
                    FROM enrollment e
                    JOIN teaching_class tc ON e.teaching_class_id = tc.id
                    WHERE tc.teacher_id = :teacher_id AND tc.year = 2025 AND tc.semester = 'spring'
                    """,
                    params,
                ).get("value")
            if can("score", "enrollment", "teaching_class"):
                cards.update(_one(
                    conn,
                    """
                    SELECT
                      ROUND(AVG(sc.final_score), 2) AS avg_score,
                      ROUND(AVG(CASE WHEN sc.final_score >= 60 THEN 1.0 ELSE 0.0 END) * 100, 2) AS pass_rate,
                      ROUND(AVG(CASE WHEN sc.final_score < 60 THEN 1.0 ELSE 0.0 END) * 100, 2) AS fail_rate
                    FROM score sc
                    JOIN enrollment e ON sc.enrollment_id = e.id
                    JOIN teaching_class tc ON e.teaching_class_id = tc.id
                    WHERE tc.teacher_id = :teacher_id
                    """,
                    params,
                ))
            if can("assignment_submission", "assignment", "teaching_class"):
                cards["assignment_submit_rate"] = _one(
                    conn,
                    """
                    SELECT ROUND(AVG(CASE WHEN sub.status <> 'missing' THEN 1.0 ELSE 0.0 END) * 100, 2) AS value
                    FROM assignment_submission sub
                    JOIN assignment a ON sub.assignment_id = a.id
                    JOIN teaching_class tc ON a.teaching_class_id = tc.id
                    WHERE tc.teacher_id = :teacher_id
                    """,
                    params,
                ).get("value")
            if can("attendance", "teaching_class"):
                cards["attendance_rate"] = _one(
                    conn,
                    """
                    SELECT ROUND(AVG(CASE WHEN a.status = 'present' THEN 1.0 ELSE 0.0 END) * 100, 2) AS value
                    FROM attendance a
                    JOIN teaching_class tc ON a.teaching_class_id = tc.id
                    WHERE tc.teacher_id = :teacher_id
                    """,
                    params,
                ).get("value")
            if can("learning_activity", "teaching_class"):
                cards["activity_records"] = _one(
                    conn,
                    """
                    SELECT COUNT(*) AS value
                    FROM learning_activity la
                    JOIN teaching_class tc ON la.teaching_class_id = tc.id
                    WHERE tc.teacher_id = :teacher_id
                    """,
                    params,
                ).get("value")
            low_score_courses = _rows(
                conn,
                """
                SELECT c.name AS course_name,
                       ROUND(AVG(sc.final_score), 2) AS avg_score,
                       COUNT(e.id) AS enrollment_count
                FROM score sc
                JOIN enrollment e ON sc.enrollment_id = e.id
                JOIN teaching_class tc ON e.teaching_class_id = tc.id
                JOIN course c ON tc.course_id = c.id
                WHERE tc.teacher_id = :teacher_id
                GROUP BY c.id, c.name
                ORDER BY avg_score ASC
                LIMIT 8
                """,
                params,
            ) if can("score", "enrollment", "teaching_class", "course") else []
            fail_rate_courses = _rows(
                conn,
                """
                SELECT c.name AS course_name,
                       ROUND(AVG(CASE WHEN sc.final_score < 60 THEN 1.0 ELSE 0.0 END) * 100, 2) AS fail_rate,
                       COUNT(e.id) AS enrollment_count
                FROM score sc
                JOIN enrollment e ON sc.enrollment_id = e.id
                JOIN teaching_class tc ON e.teaching_class_id = tc.id
                JOIN course c ON tc.course_id = c.id
                WHERE tc.teacher_id = :teacher_id
                GROUP BY c.id, c.name
                ORDER BY fail_rate DESC, enrollment_count DESC
                LIMIT 8
                """,
                params,
            ) if can("score", "enrollment", "teaching_class", "course") else []
            attendance_risk_courses = _rows(
                conn,
                """
                SELECT c.name AS course_name,
                       ROUND(AVG(CASE WHEN a.status = 'absent' THEN 1.0 ELSE 0.0 END) * 100, 2) AS absent_rate,
                       COUNT(a.id) AS attendance_count
                FROM attendance a
                JOIN teaching_class tc ON a.teaching_class_id = tc.id
                JOIN course c ON tc.course_id = c.id
                WHERE tc.teacher_id = :teacher_id
                GROUP BY c.id, c.name
                ORDER BY absent_rate DESC, attendance_count DESC
                LIMIT 8
                """,
                params,
            ) if can("attendance", "teaching_class", "course") else []
            teacher_workload = _rows(
                conn,
                """
                SELECT t.name AS teacher_name,
                       COUNT(DISTINCT tc.id) AS teaching_class_count,
                       COUNT(e.id) AS enrollment_count
                FROM teacher t
                JOIN teaching_class tc ON t.id = tc.teacher_id
                LEFT JOIN enrollment e ON tc.id = e.teaching_class_id
                WHERE t.id = :teacher_id
                GROUP BY t.id, t.name
                """,
                params,
            ) if can("teacher", "teaching_class", "enrollment") else []
        return {
            "source": source.name,
            "source_label": source.label,
            "cards": cards,
            "students_by_college": [],
            "score_distribution": [],
            "low_score_courses": low_score_courses,
            "fail_rate_courses": fail_rate_courses,
            "teacher_workload": teacher_workload,
            "college_quality": [],
            "attendance_risk_courses": attendance_risk_courses,
            "warning_by_major": [],
        }

    if row_scope.get("college_id"):
        college_id = row_scope["college_id"]
        params = {"college_id": college_id}
        with engine.connect() as conn:
            cards = {}
            if can("student"):
                cards["active_students"] = _one(
                    conn,
                    "SELECT COUNT(*) AS value FROM student WHERE status = 'active' AND college_id = :college_id",
                    params,
                ).get("value")
            if can("teacher"):
                cards["teacher_count"] = _one(
                    conn,
                    "SELECT COUNT(*) AS value FROM teacher WHERE college_id = :college_id",
                    params,
                ).get("value")
            if can("course"):
                cards["course_count"] = _one(
                    conn,
                    "SELECT COUNT(*) AS value FROM course WHERE college_id = :college_id",
                    params,
                ).get("value")
            if can("teaching_class", "course"):
                cards["current_classes"] = _one(
                    conn,
                    """
                    SELECT COUNT(*) AS value
                    FROM teaching_class tc
                    JOIN course c ON tc.course_id = c.id
                    WHERE c.college_id = :college_id AND tc.year = 2025 AND tc.semester = 'spring'
                    """,
                    params,
                ).get("value")
            if can("enrollment", "teaching_class", "course"):
                cards["current_enrollments"] = _one(
                    conn,
                    """
                    SELECT COUNT(e.id) AS value
                    FROM enrollment e
                    JOIN teaching_class tc ON e.teaching_class_id = tc.id
                    JOIN course c ON tc.course_id = c.id
                    WHERE c.college_id = :college_id AND tc.year = 2025 AND tc.semester = 'spring'
                    """,
                    params,
                ).get("value")
            if can("score", "enrollment", "teaching_class", "course"):
                cards.update(_one(
                    conn,
                    """
                    SELECT
                      ROUND(AVG(sc.final_score), 2) AS avg_score,
                      ROUND(AVG(CASE WHEN sc.final_score >= 60 THEN 1.0 ELSE 0.0 END) * 100, 2) AS pass_rate,
                      ROUND(AVG(CASE WHEN sc.final_score < 60 THEN 1.0 ELSE 0.0 END) * 100, 2) AS fail_rate
                    FROM score sc
                    JOIN enrollment e ON sc.enrollment_id = e.id
                    JOIN teaching_class tc ON e.teaching_class_id = tc.id
                    JOIN course c ON tc.course_id = c.id
                    WHERE c.college_id = :college_id
                    """,
                    params,
                ))
            if can("assignment_submission", "assignment", "teaching_class", "course"):
                cards["assignment_submit_rate"] = _one(
                    conn,
                    """
                    SELECT ROUND(AVG(CASE WHEN sub.status <> 'missing' THEN 1.0 ELSE 0.0 END) * 100, 2) AS value
                    FROM assignment_submission sub
                    JOIN assignment a ON sub.assignment_id = a.id
                    JOIN teaching_class tc ON a.teaching_class_id = tc.id
                    JOIN course c ON tc.course_id = c.id
                    WHERE c.college_id = :college_id
                    """,
                    params,
                ).get("value")
            if can("attendance", "teaching_class", "course"):
                cards["attendance_rate"] = _one(
                    conn,
                    """
                    SELECT ROUND(AVG(CASE WHEN a.status = 'present' THEN 1.0 ELSE 0.0 END) * 100, 2) AS value
                    FROM attendance a
                    JOIN teaching_class tc ON a.teaching_class_id = tc.id
                    JOIN course c ON tc.course_id = c.id
                    WHERE c.college_id = :college_id
                    """,
                    params,
                ).get("value")
            if can("academic_warning", "student"):
                cards["open_warnings"] = _one(
                    conn,
                    """
                    SELECT COUNT(*) AS value
                    FROM academic_warning w
                    JOIN student s ON w.student_id = s.id
                    WHERE w.resolved = 0 AND s.college_id = :college_id
                    """,
                    params,
                ).get("value")
            if can("learning_activity", "teaching_class", "course"):
                cards["activity_records"] = _one(
                    conn,
                    """
                    SELECT COUNT(*) AS value
                    FROM learning_activity la
                    JOIN teaching_class tc ON la.teaching_class_id = tc.id
                    JOIN course c ON tc.course_id = c.id
                    WHERE c.college_id = :college_id
                    """,
                    params,
                ).get("value")

            students_by_college = _rows(
                conn,
                """
                SELECT c.name AS label, COUNT(s.id) AS value
                FROM college c
                LEFT JOIN student s ON s.college_id = c.id AND s.status = 'active'
                WHERE c.id = :college_id
                GROUP BY c.id, c.name
                """,
                params,
            ) if can("college", "student") else []
            low_score_courses = _rows(
                conn,
                """
                SELECT c.name AS course_name,
                       ROUND(AVG(sc.final_score), 2) AS avg_score,
                       COUNT(e.id) AS enrollment_count
                FROM score sc
                JOIN enrollment e ON sc.enrollment_id = e.id
                JOIN teaching_class tc ON e.teaching_class_id = tc.id
                JOIN course c ON tc.course_id = c.id
                WHERE c.college_id = :college_id
                GROUP BY c.id, c.name
                ORDER BY avg_score ASC
                LIMIT 8
                """,
                params,
            ) if can("score", "enrollment", "teaching_class", "course") else []
            fail_rate_courses = _rows(
                conn,
                """
                SELECT c.name AS course_name,
                       ROUND(AVG(CASE WHEN sc.final_score < 60 THEN 1.0 ELSE 0.0 END) * 100, 2) AS fail_rate,
                       COUNT(e.id) AS enrollment_count
                FROM score sc
                JOIN enrollment e ON sc.enrollment_id = e.id
                JOIN teaching_class tc ON e.teaching_class_id = tc.id
                JOIN course c ON tc.course_id = c.id
                WHERE c.college_id = :college_id
                GROUP BY c.id, c.name
                ORDER BY fail_rate DESC, enrollment_count DESC
                LIMIT 8
                """,
                params,
            ) if can("score", "enrollment", "teaching_class", "course") else []
            teacher_workload = _rows(
                conn,
                """
                SELECT t.name AS teacher_name,
                       COUNT(DISTINCT tc.id) AS teaching_class_count,
                       COUNT(e.id) AS enrollment_count
                FROM teacher t
                JOIN teaching_class tc ON t.id = tc.teacher_id
                LEFT JOIN enrollment e ON tc.id = e.teaching_class_id
                WHERE t.college_id = :college_id
                GROUP BY t.id, t.name
                ORDER BY teaching_class_count DESC, enrollment_count DESC
                LIMIT 8
                """,
                params,
            ) if can("teacher", "teaching_class", "enrollment") else []
            college_quality = _rows(
                conn,
                """
                SELECT co.name AS college_name,
                       ROUND(AVG(sc.final_score), 2) AS avg_score,
                       ROUND(AVG(CASE WHEN sc.final_score < 60 THEN 1.0 ELSE 0.0 END) * 100, 2) AS fail_rate
                FROM score sc
                JOIN enrollment e ON sc.enrollment_id = e.id
                JOIN student s ON e.student_id = s.id
                JOIN college co ON s.college_id = co.id
                WHERE co.id = :college_id
                GROUP BY co.id, co.name
                """,
                params,
            ) if can("score", "enrollment", "student", "college") else []
            attendance_risk_courses = _rows(
                conn,
                """
                SELECT c.name AS course_name,
                       ROUND(AVG(CASE WHEN a.status = 'absent' THEN 1.0 ELSE 0.0 END) * 100, 2) AS absent_rate,
                       COUNT(a.id) AS attendance_count
                FROM attendance a
                JOIN teaching_class tc ON a.teaching_class_id = tc.id
                JOIN course c ON tc.course_id = c.id
                WHERE c.college_id = :college_id
                GROUP BY c.id, c.name
                ORDER BY absent_rate DESC, attendance_count DESC
                LIMIT 8
                """,
                params,
            ) if can("attendance", "teaching_class", "course") else []
            warning_by_major = _rows(
                conn,
                """
                SELECT m.name AS major_name,
                       COUNT(w.id) AS warning_count,
                       ROUND(AVG(w.risk_score), 1) AS avg_risk_score
                FROM academic_warning w
                JOIN student s ON w.student_id = s.id
                JOIN major m ON s.major_id = m.id
                WHERE w.resolved = 0 AND s.college_id = :college_id
                GROUP BY m.id, m.name
                ORDER BY warning_count DESC, avg_risk_score DESC
                LIMIT 8
                """,
                params,
            ) if can("academic_warning", "student", "major") else []
        return {
            "source": source.name,
            "source_label": source.label,
            "cards": cards,
            "students_by_college": students_by_college,
            "score_distribution": [],
            "low_score_courses": low_score_courses,
            "fail_rate_courses": fail_rate_courses,
            "teacher_workload": teacher_workload,
            "college_quality": college_quality,
            "attendance_risk_courses": attendance_risk_courses,
            "warning_by_major": warning_by_major,
        }
    with engine.connect() as conn:
        filter_options = _filter_options(conn)
        cards: dict[str, Any] = {}
        if can("student"):
            params: dict[str, Any] = {}
            needs_course_scope = bool(filters.get("year") or filters.get("course_type"))
            if needs_course_scope:
                cards["active_students"] = _one(
                    conn,
                    f"""
                    SELECT COUNT(DISTINCT s.id) AS value
                    FROM student s
                    JOIN enrollment e ON e.student_id = s.id
                    JOIN teaching_class tc ON e.teaching_class_id = tc.id
                    JOIN course c ON tc.course_id = c.id
                    WHERE s.status = 'active'{_apply_filters(filters, params, student_alias="s", course_alias="c", class_alias="tc")}
                    """,
                    params,
                ).get("value")
            else:
                cards["active_students"] = _one(
                    conn,
                    f"SELECT COUNT(DISTINCT s.id) AS value FROM student s WHERE s.status = 'active'{_apply_filters(filters, params, student_alias='s')}",
                    params,
                ).get("value")
        if can("teacher"):
            params = {}
            cards["teacher_count"] = _one(
                conn,
                f"""
                SELECT COUNT(DISTINCT t.id) AS value
                FROM teacher t
                JOIN teaching_class tc ON t.id = tc.teacher_id
                JOIN course c ON tc.course_id = c.id
                WHERE 1 = 1{_apply_filters(filters, params, course_alias="c", class_alias="tc")}
                """,
                params,
            ).get("value")
        if can("course"):
            params = {}
            cards["course_count"] = _one(
                conn,
                f"""
                SELECT COUNT(DISTINCT c.id) AS value
                FROM course c
                LEFT JOIN teaching_class tc ON tc.course_id = c.id
                WHERE 1 = 1{_apply_filters(filters, params, course_alias="c", class_alias="tc")}
                """,
                params,
            ).get("value")
        if can("teaching_class"):
            params = {}
            cards["current_classes"] = _one(
                conn,
                f"""
                SELECT COUNT(DISTINCT tc.id) AS value
                FROM teaching_class tc
                JOIN course c ON tc.course_id = c.id
                LEFT JOIN enrollment e ON e.teaching_class_id = tc.id
                LEFT JOIN student s ON e.student_id = s.id
                WHERE 1 = 1{_apply_filters(filters, params, student_alias="s", course_alias="c", class_alias="tc")}
                """,
                params,
            ).get("value")
        if can("enrollment", "teaching_class"):
            params = {}
            cards["current_enrollments"] = _one(
                conn,
                f"""
                SELECT COUNT(DISTINCT e.id) AS value
                FROM enrollment e
                JOIN teaching_class tc ON e.teaching_class_id = tc.id
                JOIN course c ON tc.course_id = c.id
                JOIN student s ON e.student_id = s.id
                WHERE 1 = 1{_apply_filters(filters, params, student_alias="s", course_alias="c", class_alias="tc")}
                """,
                params,
            ).get("value")
        if can("score", "enrollment", "teaching_class", "course", "student"):
            params = {}
            score_cards = _one(
                conn,
                f"""
                SELECT
                  ROUND(AVG(sc.final_score), 2) AS avg_score,
                  ROUND(AVG(CASE WHEN sc.final_score >= 60 THEN 1.0 ELSE 0.0 END) * 100, 2) AS pass_rate,
                  ROUND(AVG(CASE WHEN sc.final_score < 60 THEN 1.0 ELSE 0.0 END) * 100, 2) AS fail_rate
                FROM score sc
                JOIN enrollment e ON sc.enrollment_id = e.id
                JOIN teaching_class tc ON e.teaching_class_id = tc.id
                JOIN course c ON tc.course_id = c.id
                JOIN student s ON e.student_id = s.id
                WHERE 1 = 1{_apply_filters(filters, params, student_alias="s", course_alias="c", class_alias="tc")}
                """,
                params,
            )
            cards.update(score_cards)
        if can("assignment_submission", "assignment", "teaching_class", "course", "student"):
            params = {}
            cards["assignment_submit_rate"] = _one(
                conn,
                f"""
                SELECT ROUND(AVG(CASE WHEN sub.status <> 'missing' THEN 1.0 ELSE 0.0 END) * 100, 2) AS value
                FROM assignment_submission sub
                JOIN assignment a ON sub.assignment_id = a.id
                JOIN teaching_class tc ON a.teaching_class_id = tc.id
                JOIN course c ON tc.course_id = c.id
                JOIN student s ON sub.student_id = s.id
                WHERE 1 = 1{_apply_filters(filters, params, student_alias="s", course_alias="c", class_alias="tc")}
                """,
                params,
            ).get("value")
        if can("attendance", "teaching_class", "course", "student"):
            params = {}
            cards["attendance_rate"] = _one(
                conn,
                f"""
                SELECT ROUND(AVG(CASE WHEN a.status = 'present' THEN 1.0 ELSE 0.0 END) * 100, 2) AS value
                FROM attendance a
                JOIN teaching_class tc ON a.teaching_class_id = tc.id
                JOIN course c ON tc.course_id = c.id
                JOIN student s ON a.student_id = s.id
                WHERE 1 = 1{_apply_filters(filters, params, student_alias="s", course_alias="c", class_alias="tc")}
                """,
                params,
            ).get("value")
        if can("academic_warning", "student"):
            params = {}
            cards["open_warnings"] = _one(
                conn,
                f"""
                SELECT COUNT(DISTINCT w.id) AS value
                FROM academic_warning w
                JOIN student s ON w.student_id = s.id
                WHERE w.resolved = 0{_apply_filters(filters, params, student_alias="s", warning_alias="w")}
                """,
                params,
            ).get("value")
        if can("learning_activity", "teaching_class", "course", "student"):
            params = {}
            cards["activity_records"] = _one(
                conn,
                f"""
                SELECT COUNT(DISTINCT la.id) AS value
                FROM learning_activity la
                JOIN teaching_class tc ON la.teaching_class_id = tc.id
                JOIN course c ON tc.course_id = c.id
                JOIN student s ON la.student_id = s.id
                WHERE 1 = 1{_apply_filters(filters, params, student_alias="s", course_alias="c", class_alias="tc")}
                """,
                params,
            ).get("value")

        params = {}
        students_by_college = _rows(
            conn,
            f"""
            SELECT c.name AS label, COUNT(DISTINCT s.id) AS value
            FROM college c
            LEFT JOIN student s ON s.college_id = c.id AND s.status = 'active'
            LEFT JOIN enrollment e ON e.student_id = s.id
            LEFT JOIN teaching_class tc ON e.teaching_class_id = tc.id
            LEFT JOIN course crs ON tc.course_id = crs.id
            WHERE 1 = 1{_apply_filters(filters, params, student_alias="s", course_alias="crs", class_alias="tc")}
            GROUP BY c.id, c.name
            ORDER BY value DESC
            """,
            params,
        ) if can("college", "student") else []

        params = {}
        score_distribution = _rows(
            conn,
            f"""
            SELECT bucket AS label, COUNT(*) AS value
            FROM (
              SELECT CASE
                WHEN sc.final_score < 60 THEN '0-59'
                WHEN sc.final_score < 70 THEN '60-69'
                WHEN sc.final_score < 80 THEN '70-79'
                WHEN sc.final_score < 90 THEN '80-89'
                ELSE '90-100'
              END AS bucket,
              CASE
                WHEN sc.final_score < 60 THEN 1
                WHEN sc.final_score < 70 THEN 2
                WHEN sc.final_score < 80 THEN 3
                WHEN sc.final_score < 90 THEN 4
                ELSE 5
              END AS bucket_order
              FROM score sc
              JOIN enrollment e ON sc.enrollment_id = e.id
              JOIN teaching_class tc ON e.teaching_class_id = tc.id
              JOIN course c ON tc.course_id = c.id
              JOIN student s ON e.student_id = s.id
              WHERE 1 = 1{_apply_filters(filters, params, student_alias="s", course_alias="c", class_alias="tc", college_scope="course")}
            )
            GROUP BY bucket, bucket_order
            ORDER BY bucket_order
            """,
            params,
        ) if can("score") else []

        params = {}
        low_score_courses = _rows(
            conn,
            f"""
            SELECT c.name AS course_name,
                   ROUND(AVG(sc.final_score), 2) AS avg_score,
                   COUNT(e.id) AS enrollment_count
            FROM score sc
            JOIN enrollment e ON sc.enrollment_id = e.id
            JOIN teaching_class tc ON e.teaching_class_id = tc.id
            JOIN course c ON tc.course_id = c.id
            JOIN student s ON e.student_id = s.id
            WHERE 1 = 1{_apply_filters(filters, params, student_alias="s", course_alias="c", class_alias="tc", college_scope="course")}
            GROUP BY c.id, c.name
            ORDER BY avg_score ASC
            LIMIT 8
            """,
            params,
        ) if can("score", "enrollment", "teaching_class", "course") else []

        params = {}
        fail_rate_courses = _rows(
            conn,
            f"""
            SELECT c.name AS course_name,
                   ROUND(AVG(CASE WHEN sc.final_score < 60 THEN 1.0 ELSE 0.0 END) * 100, 2) AS fail_rate,
                   COUNT(e.id) AS enrollment_count
            FROM score sc
            JOIN enrollment e ON sc.enrollment_id = e.id
            JOIN teaching_class tc ON e.teaching_class_id = tc.id
            JOIN course c ON tc.course_id = c.id
            JOIN student s ON e.student_id = s.id
            WHERE 1 = 1{_apply_filters(filters, params, student_alias="s", course_alias="c", class_alias="tc", college_scope="course")}
            GROUP BY c.id, c.name
            ORDER BY fail_rate DESC, enrollment_count DESC
            LIMIT 8
            """,
            params,
        ) if can("score", "enrollment", "teaching_class", "course") else []

        params = {}
        teacher_workload = _rows(
            conn,
            f"""
            SELECT t.name AS teacher_name,
                   COUNT(DISTINCT tc.id) AS teaching_class_count,
                   COUNT(e.id) AS enrollment_count
            FROM teacher t
            JOIN teaching_class tc ON t.id = tc.teacher_id
            JOIN course c ON tc.course_id = c.id
            LEFT JOIN enrollment e ON tc.id = e.teaching_class_id
            LEFT JOIN student s ON e.student_id = s.id
            WHERE 1 = 1{_apply_filters(filters, params, student_alias="s", course_alias="c", class_alias="tc", college_scope="course")}
            GROUP BY t.id, t.name
            ORDER BY teaching_class_count DESC, enrollment_count DESC
            LIMIT 8
            """,
            params,
        ) if can("teacher", "teaching_class", "enrollment") else []

        params = {}
        college_quality = _rows(
            conn,
            f"""
            SELECT co.name AS college_name,
                   ROUND(AVG(sc.final_score), 2) AS avg_score,
                   ROUND(AVG(CASE WHEN sc.final_score < 60 THEN 1.0 ELSE 0.0 END) * 100, 2) AS fail_rate
            FROM score sc
            JOIN enrollment e ON sc.enrollment_id = e.id
            JOIN student s ON e.student_id = s.id
            JOIN teaching_class tc ON e.teaching_class_id = tc.id
            JOIN course c ON tc.course_id = c.id
            JOIN college co ON c.college_id = co.id
            WHERE 1 = 1{_apply_filters(filters, params, student_alias="s", course_alias="c", class_alias="tc", college_scope="course")}
            GROUP BY co.id, co.name
            ORDER BY avg_score DESC
            """,
            params,
        ) if can("score", "enrollment", "student", "college") else []

        params = {}
        attendance_risk_courses = _rows(
            conn,
            f"""
            SELECT c.name AS course_name,
                   ROUND(AVG(CASE WHEN a.status = 'absent' THEN 1.0 ELSE 0.0 END) * 100, 2) AS absent_rate,
                   COUNT(a.id) AS attendance_count
            FROM attendance a
            JOIN teaching_class tc ON a.teaching_class_id = tc.id
            JOIN course c ON tc.course_id = c.id
            JOIN student s ON a.student_id = s.id
            WHERE 1 = 1{_apply_filters(filters, params, student_alias="s", course_alias="c", class_alias="tc", college_scope="course")}
            GROUP BY c.id, c.name
            ORDER BY absent_rate DESC, attendance_count DESC
            LIMIT 8
            """,
            params,
        ) if can("attendance", "teaching_class", "course") else []

        params = {}
        warning_by_major = _rows(
            conn,
            f"""
            SELECT m.name AS major_name,
                   COUNT(w.id) AS warning_count,
                   ROUND(AVG(w.risk_score), 1) AS avg_risk_score
            FROM academic_warning w
            JOIN student s ON w.student_id = s.id
            JOIN major m ON s.major_id = m.id
            WHERE w.resolved = 0{_apply_filters(filters, params, student_alias="s", warning_alias="w")}
            GROUP BY m.id, m.name
            ORDER BY warning_count DESC, avg_risk_score DESC
            LIMIT 8
            """,
            params,
        ) if can("academic_warning", "student", "major") else []

    return {
        "source": source.name,
        "source_label": source.label,
        "cards": cards,
        "students_by_college": students_by_college,
        "score_distribution": score_distribution,
        "low_score_courses": low_score_courses,
        "fail_rate_courses": fail_rate_courses,
        "teacher_workload": teacher_workload,
        "college_quality": college_quality,
        "attendance_risk_courses": attendance_risk_courses,
        "warning_by_major": warning_by_major,
        "filter_options": filter_options,
        "filters": filters,
    }
