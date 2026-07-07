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


def teaching_dashboard(source_name: str = "teaching", allowed_tables: set[str] | frozenset[str] | None = None) -> dict[str, Any]:
    source = get_source(source_name)
    if source.name != "teaching":
        raise ValueError("teaching dashboard only supports the teaching data source")
    allowed = set(allowed_tables or [])
    unrestricted = not allowed

    def can(*tables: str) -> bool:
        return unrestricted or set(tables).issubset(allowed)

    engine = get_engine(source)
    with engine.connect() as conn:
        cards: dict[str, Any] = {}
        if can("student"):
            cards["active_students"] = _one(conn, "SELECT COUNT(*) AS value FROM student WHERE status = 'active'").get("value")
        if can("teacher"):
            cards["teacher_count"] = _one(conn, "SELECT COUNT(*) AS value FROM teacher").get("value")
        if can("course"):
            cards["course_count"] = _one(conn, "SELECT COUNT(*) AS value FROM course").get("value")
        if can("teaching_class"):
            cards["current_classes"] = _one(
                conn,
                "SELECT COUNT(*) AS value FROM teaching_class WHERE year = 2025 AND semester = 'spring'",
            ).get("value")
        if can("enrollment", "teaching_class"):
            cards["current_enrollments"] = _one(
                conn,
                """
                SELECT COUNT(*) AS value FROM enrollment e JOIN teaching_class tc ON e.teaching_class_id = tc.id
                WHERE tc.year = 2025 AND tc.semester = 'spring'
                """,
            ).get("value")
        if can("score"):
            score_cards = _one(
                conn,
                """
                SELECT
                  ROUND(AVG(final_score), 2) AS avg_score,
                  ROUND(AVG(CASE WHEN final_score >= 60 THEN 1.0 ELSE 0.0 END) * 100, 2) AS pass_rate,
                  ROUND(AVG(CASE WHEN final_score < 60 THEN 1.0 ELSE 0.0 END) * 100, 2) AS fail_rate
                FROM score
                """,
            )
            cards.update(score_cards)

        students_by_college = _rows(
            conn,
            """
            SELECT c.name AS label, COUNT(s.id) AS value
            FROM college c
            LEFT JOIN student s ON s.college_id = c.id AND s.status = 'active'
            GROUP BY c.id, c.name
            ORDER BY value DESC
            """,
        ) if can("college", "student") else []

        score_distribution = _rows(
            conn,
            """
            SELECT bucket AS label, COUNT(*) AS value
            FROM (
              SELECT CASE
                WHEN final_score < 60 THEN '0-59'
                WHEN final_score < 70 THEN '60-69'
                WHEN final_score < 80 THEN '70-79'
                WHEN final_score < 90 THEN '80-89'
                ELSE '90-100'
              END AS bucket,
              CASE
                WHEN final_score < 60 THEN 1
                WHEN final_score < 70 THEN 2
                WHEN final_score < 80 THEN 3
                WHEN final_score < 90 THEN 4
                ELSE 5
              END AS bucket_order
              FROM score
            )
            GROUP BY bucket, bucket_order
            ORDER BY bucket_order
            """,
        ) if can("score") else []

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
            GROUP BY c.id, c.name
            ORDER BY avg_score ASC
            LIMIT 8
            """,
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
            GROUP BY c.id, c.name
            ORDER BY fail_rate DESC, enrollment_count DESC
            LIMIT 8
            """,
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
            GROUP BY t.id, t.name
            ORDER BY teaching_class_count DESC, enrollment_count DESC
            LIMIT 8
            """,
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
            GROUP BY co.id, co.name
            ORDER BY avg_score DESC
            """,
        ) if can("score", "enrollment", "student", "college") else []

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
    }
