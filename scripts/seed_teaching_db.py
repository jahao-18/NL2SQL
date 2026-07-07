"""Seed a teaching-domain SQLite database for the course project.

The generated data is deterministic and intentionally contains visible
patterns: some courses are harder, some colleges have slightly different
score levels, and teachers have different workloads. This makes dashboard
and NL2SQL demos easier to verify.
"""
from __future__ import annotations

import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "teaching.db"

DDL = [
    """
    CREATE TABLE college (
        id      INTEGER PRIMARY KEY,  -- 学院ID
        code    TEXT NOT NULL UNIQUE, -- 学院编码
        name    TEXT NOT NULL         -- 学院名称
    )
    """,
    """
    CREATE TABLE major (
        id         INTEGER PRIMARY KEY,  -- 专业ID
        college_id INTEGER NOT NULL,     -- 所属学院ID
        code       TEXT NOT NULL UNIQUE, -- 专业编码
        name       TEXT NOT NULL,        -- 专业名称
        FOREIGN KEY (college_id) REFERENCES college(id)
    )
    """,
    """
    CREATE TABLE class_group (
        id         INTEGER PRIMARY KEY, -- 班级ID
        major_id   INTEGER NOT NULL,    -- 所属专业ID
        name       TEXT NOT NULL,       -- 班级名称
        grade_year INTEGER NOT NULL,    -- 年级
        FOREIGN KEY (major_id) REFERENCES major(id)
    )
    """,
    """
    CREATE TABLE student (
        id              INTEGER PRIMARY KEY,  -- 学生ID
        student_no      TEXT NOT NULL UNIQUE, -- 学号
        name            TEXT NOT NULL,        -- 学生姓名
        gender          TEXT NOT NULL,        -- 性别: male/female
        college_id      INTEGER NOT NULL,     -- 所属学院ID
        major_id        INTEGER NOT NULL,     -- 所属专业ID
        class_id        INTEGER NOT NULL,     -- 所属班级ID
        enrollment_year INTEGER NOT NULL,     -- 入学年份
        status          TEXT NOT NULL,        -- 学籍状态: active/graduated/suspended
        FOREIGN KEY (college_id) REFERENCES college(id),
        FOREIGN KEY (major_id) REFERENCES major(id),
        FOREIGN KEY (class_id) REFERENCES class_group(id)
    )
    """,
    """
    CREATE TABLE teacher (
        id         INTEGER PRIMARY KEY,  -- 教师ID
        teacher_no TEXT NOT NULL UNIQUE, -- 工号
        name       TEXT NOT NULL,        -- 教师姓名
        gender     TEXT NOT NULL,        -- 性别: male/female
        college_id INTEGER NOT NULL,     -- 所属学院ID
        title      TEXT NOT NULL,        -- 职称
        hire_date  TEXT NOT NULL,        -- 入职日期
        FOREIGN KEY (college_id) REFERENCES college(id)
    )
    """,
    """
    CREATE TABLE course (
        id          INTEGER PRIMARY KEY,  -- 课程ID
        course_code TEXT NOT NULL UNIQUE, -- 课程编码
        name        TEXT NOT NULL,        -- 课程名称
        credit      REAL NOT NULL,        -- 学分
        course_type TEXT NOT NULL,        -- 课程类型: required/elective/general
        college_id  INTEGER NOT NULL,     -- 开课学院ID
        difficulty  REAL NOT NULL,        -- 难度系数,数值越高平均成绩越低
        FOREIGN KEY (college_id) REFERENCES college(id)
    )
    """,
    """
    CREATE TABLE teaching_class (
        id        INTEGER PRIMARY KEY, -- 开课班ID
        course_id INTEGER NOT NULL,    -- 课程ID
        teacher_id INTEGER NOT NULL,   -- 任课教师ID
        year      INTEGER NOT NULL,    -- 开课年份
        semester  TEXT NOT NULL,       -- 学期: spring/autumn
        capacity  INTEGER NOT NULL,    -- 课程容量
        classroom TEXT NOT NULL,       -- 教室
        FOREIGN KEY (course_id) REFERENCES course(id),
        FOREIGN KEY (teacher_id) REFERENCES teacher(id)
    )
    """,
    """
    CREATE TABLE enrollment (
        id                INTEGER PRIMARY KEY, -- 选课ID
        teaching_class_id INTEGER NOT NULL,    -- 开课班ID
        student_id        INTEGER NOT NULL,    -- 学生ID
        enroll_time       TEXT NOT NULL,       -- 选课时间
        FOREIGN KEY (teaching_class_id) REFERENCES teaching_class(id),
        FOREIGN KEY (student_id) REFERENCES student(id)
    )
    """,
    """
    CREATE TABLE score (
        id            INTEGER PRIMARY KEY, -- 成绩ID
        enrollment_id INTEGER NOT NULL,    -- 选课ID
        usual_score   REAL NOT NULL,       -- 平时成绩
        exam_score    REAL NOT NULL,       -- 考试成绩
        final_score   REAL NOT NULL,       -- 总评成绩
        grade_point   REAL NOT NULL,       -- 绩点
        passed        INTEGER NOT NULL,    -- 是否通过: 1=通过,0=未通过
        FOREIGN KEY (enrollment_id) REFERENCES enrollment(id)
    )
    """,
    """
    CREATE TABLE evaluation (
        id                INTEGER PRIMARY KEY, -- 教学评价ID
        teaching_class_id INTEGER NOT NULL,    -- 开课班ID
        student_id        INTEGER NOT NULL,    -- 学生ID
        score             REAL NOT NULL,       -- 教学评价分数,1-5
        comment           TEXT,                -- 评价内容
        FOREIGN KEY (teaching_class_id) REFERENCES teaching_class(id),
        FOREIGN KEY (student_id) REFERENCES student(id)
    )
    """,
]

INDEXES = [
    "CREATE INDEX idx_major_college ON major(college_id)",
    "CREATE INDEX idx_class_major ON class_group(major_id)",
    "CREATE INDEX idx_student_college ON student(college_id)",
    "CREATE INDEX idx_student_major ON student(major_id)",
    "CREATE INDEX idx_student_class ON student(class_id)",
    "CREATE INDEX idx_teacher_college ON teacher(college_id)",
    "CREATE INDEX idx_course_college ON course(college_id)",
    "CREATE INDEX idx_teaching_class_course ON teaching_class(course_id)",
    "CREATE INDEX idx_teaching_class_teacher ON teaching_class(teacher_id)",
    "CREATE INDEX idx_teaching_class_term ON teaching_class(year, semester)",
    "CREATE INDEX idx_enrollment_class ON enrollment(teaching_class_id)",
    "CREATE INDEX idx_enrollment_student ON enrollment(student_id)",
    "CREATE INDEX idx_score_enrollment ON score(enrollment_id)",
    "CREATE INDEX idx_score_final ON score(final_score)",
    "CREATE INDEX idx_evaluation_class ON evaluation(teaching_class_id)",
]

COLLEGES = [
    (1, "CS", "计算机学院"),
    (2, "MATH", "数学与统计学院"),
    (3, "BUS", "经济管理学院"),
    (4, "ART", "人文与艺术学院"),
]

MAJORS = [
    (1, 1, "SE", "软件工程"),
    (2, 1, "CS", "计算机科学与技术"),
    (3, 1, "AI", "人工智能"),
    (4, 2, "MATH", "数学与应用数学"),
    (5, 2, "STAT", "统计学"),
    (6, 3, "ACCT", "会计学"),
    (7, 3, "MKT", "市场营销"),
    (8, 4, "CHN", "汉语言文学"),
    (9, 4, "DESIGN", "视觉传达设计"),
]

COURSE_NAMES = {
    1: ["程序设计基础", "数据结构", "数据库系统", "操作系统", "计算机网络", "软件工程", "Web 开发技术", "机器学习基础"],
    2: ["高等数学", "线性代数", "概率论与数理统计", "数学分析", "离散数学", "回归分析"],
    3: ["管理学原理", "会计学基础", "市场营销", "财务管理", "运营管理", "商业数据分析"],
    4: ["大学语文", "中国文学史", "艺术概论", "新媒体设计", "写作基础", "美学原理"],
}

SURNAMES = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费廉岑薛雷贺倪汤"
GIVEN_NAMES = [
    "伟", "芳", "娜", "敏", "静", "强", "磊", "军", "洋", "勇", "艳", "杰", "娟", "涛", "明", "超",
    "秀英", "华", "慧", "巍", "晨", "昊", "雨桐", "子涵", "梓轩", "一诺", "思源", "嘉怡", "浩然", "佳琪",
]
TITLES = ["助教", "讲师", "副教授", "教授"]
ROOMS = ["A101", "A202", "B305", "C210", "D406", "实验楼 301", "实验楼 502", "图书馆报告厅"]
EVAL_COMMENTS = [
    "讲解清晰,课堂节奏合适",
    "案例丰富,有助于理解",
    "作业反馈及时",
    "课程难度较高,但收获很大",
    "希望增加更多实践环节",
    "课堂互动较好",
]


def make_name() -> str:
    return random.choice(SURNAMES) + random.choice(GIVEN_NAMES)


def clamp_score(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 1)


def grade_point(final_score: float) -> float:
    if final_score < 60:
        return 0.0
    return round(min(4.0, (final_score - 50.0) / 10.0), 1)


def term_start(year: int, semester: str) -> datetime:
    return datetime(year, 3, 1) if semester == "spring" else datetime(year, 9, 1)


def generate_classes() -> list[tuple]:
    rows = []
    class_id = 1
    for major_id, _college_id, code, _name in MAJORS:
        for grade_year in [2022, 2023, 2024, 2025]:
            for idx in range(1, 3):
                rows.append((class_id, major_id, f"{code}{grade_year % 100}{idx:02d}", grade_year))
                class_id += 1
    return rows


def generate_students(classes: list[tuple]) -> list[tuple]:
    major_to_college = {major_id: college_id for major_id, college_id, _code, _name in MAJORS}
    rows = []
    student_id = 1
    for class_id, major_id, class_name, grade_year in classes:
        college_id = major_to_college[major_id]
        size = random.randint(26, 38)
        for idx in range(1, size + 1):
            status = random.choices(["active", "graduated", "suspended"], weights=[92, 5, 3])[0]
            student_no = f"{grade_year}{major_id:02d}{class_id:03d}{idx:02d}"
            rows.append((
                student_id,
                student_no,
                make_name(),
                random.choice(["male", "female"]),
                college_id,
                major_id,
                class_id,
                grade_year,
                status,
            ))
            student_id += 1
    return rows


def generate_teachers() -> list[tuple]:
    rows = []
    teacher_id = 1
    for college_id, _code, _name in COLLEGES:
        for idx in range(1, 19):
            title = random.choices(TITLES, weights=[12, 45, 30, 13])[0]
            hire_year = random.randint(2005, 2024)
            rows.append((
                teacher_id,
                f"T{college_id}{idx:03d}",
                make_name(),
                random.choice(["male", "female"]),
                college_id,
                title,
                f"{hire_year}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
            ))
            teacher_id += 1
    return rows


def generate_courses() -> list[tuple]:
    rows = []
    course_id = 1
    type_pool = ["required", "elective", "general"]
    for college_id, code, _name in COLLEGES:
        for idx, course_name in enumerate(COURSE_NAMES[college_id], start=1):
            course_type = random.choices(type_pool, weights=[55, 30, 15])[0]
            credit = random.choice([2.0, 2.5, 3.0, 3.5, 4.0])
            base_difficulty = {
                "数据结构": 1.25,
                "操作系统": 1.35,
                "数据库系统": 1.15,
                "数学分析": 1.35,
                "概率论与数理统计": 1.2,
                "财务管理": 1.1,
            }.get(course_name, random.uniform(0.75, 1.1))
            rows.append((
                course_id,
                f"{code}{idx:03d}",
                course_name,
                credit,
                course_type,
                college_id,
                round(base_difficulty, 2),
            ))
            course_id += 1
    return rows


def generate_teaching_classes(courses: list[tuple], teachers: list[tuple]) -> list[tuple]:
    rows = []
    class_id = 1
    teachers_by_college: dict[int, list[tuple]] = {}
    for teacher in teachers:
        teachers_by_college.setdefault(teacher[4], []).append(teacher)
    for year in [2024, 2025]:
        for semester in ["spring", "autumn"]:
            for course in courses:
                course_id, _code, _name, _credit, course_type, college_id, _difficulty = course
                sections = 2 if course_type == "required" else random.choice([1, 1, 2])
                for _ in range(sections):
                    teacher = random.choice(teachers_by_college[college_id])
                    capacity = random.choice([45, 60, 80, 100, 120])
                    rows.append((
                        class_id,
                        course_id,
                        teacher[0],
                        year,
                        semester,
                        capacity,
                        random.choice(ROOMS),
                    ))
                    class_id += 1
    return rows


def generate_enrollments(
    students: list[tuple],
    courses: list[tuple],
    teaching_classes: list[tuple],
) -> tuple[list[tuple], list[tuple], list[tuple]]:
    course_by_id = {course[0]: course for course in courses}
    classes_by_college: dict[int, list[tuple]] = {}
    for tc in teaching_classes:
        college_id = course_by_id[tc[1]][5]
        classes_by_college.setdefault(college_id, []).append(tc)

    enrollments = []
    scores = []
    evaluations = []
    enrollment_id = 1
    score_id = 1
    evaluation_id = 1

    college_score_bias = {1: 1.5, 2: -1.0, 3: 2.0, 4: 3.0}
    teacher_quality: dict[int, float] = {}

    for student in students:
        if student[8] != "active":
            continue
        student_id = student[0]
        college_id = student[4]
        mixed = classes_by_college[college_id] + random.sample(teaching_classes, k=10)
        candidate_classes = list({tc[0]: tc for tc in mixed}.values())
        selected = random.sample(candidate_classes, k=random.randint(6, 10))
        for tc in selected:
            teaching_class_id, course_id, teacher_id, year, semester, _capacity, _room = tc
            start = term_start(year, semester)
            enroll_time = start + timedelta(days=random.randint(0, 20), hours=random.randint(0, 23))
            enrollments.append((enrollment_id, teaching_class_id, student_id, enroll_time.isoformat(timespec="seconds")))

            course = course_by_id[course_id]
            difficulty = course[6]
            teacher_quality.setdefault(teacher_id, random.uniform(-2.5, 3.0))
            mean = 78.0 + college_score_bias.get(course[5], 0.0) + teacher_quality[teacher_id] - difficulty * 8.0
            exam = clamp_score(random.gauss(mean, 11.0))
            usual = clamp_score(random.gauss(mean + 5.0, 7.0))
            final = clamp_score(usual * 0.4 + exam * 0.6)
            passed = 1 if final >= 60 else 0
            scores.append((score_id, enrollment_id, usual, exam, final, grade_point(final), passed))

            if random.random() < 0.72:
                eval_score = round(max(1.0, min(5.0, random.gauss(4.2 + teacher_quality[teacher_id] / 8.0, 0.45))), 1)
                evaluations.append((
                    evaluation_id,
                    teaching_class_id,
                    student_id,
                    eval_score,
                    random.choice(EVAL_COMMENTS),
                ))
                evaluation_id += 1

            enrollment_id += 1
            score_id += 1

    return enrollments, scores, evaluations


def main() -> None:
    random.seed(20260707)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON")

    for stmt in DDL:
        cur.execute(stmt)

    cur.executemany("INSERT INTO college VALUES (?, ?, ?)", COLLEGES)
    cur.executemany("INSERT INTO major VALUES (?, ?, ?, ?)", MAJORS)

    classes = generate_classes()
    cur.executemany("INSERT INTO class_group VALUES (?, ?, ?, ?)", classes)

    students = generate_students(classes)
    cur.executemany("INSERT INTO student VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", students)

    teachers = generate_teachers()
    cur.executemany("INSERT INTO teacher VALUES (?, ?, ?, ?, ?, ?, ?)", teachers)

    courses = generate_courses()
    cur.executemany("INSERT INTO course VALUES (?, ?, ?, ?, ?, ?, ?)", courses)

    teaching_classes = generate_teaching_classes(courses, teachers)
    cur.executemany("INSERT INTO teaching_class VALUES (?, ?, ?, ?, ?, ?, ?)", teaching_classes)

    enrollments, scores, evaluations = generate_enrollments(students, courses, teaching_classes)
    cur.executemany("INSERT INTO enrollment VALUES (?, ?, ?, ?)", enrollments)
    cur.executemany("INSERT INTO score VALUES (?, ?, ?, ?, ?, ?, ?)", scores)
    cur.executemany("INSERT INTO evaluation VALUES (?, ?, ?, ?, ?)", evaluations)

    for stmt in INDEXES:
        cur.execute(stmt)

    conn.commit()

    print(f"OK: seed teaching db -> {DB_PATH}")
    for table in [
        "college",
        "major",
        "class_group",
        "student",
        "teacher",
        "course",
        "teaching_class",
        "enrollment",
        "score",
        "evaluation",
    ]:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count}")

    avg_score, fail_rate = conn.execute(
        "SELECT ROUND(AVG(final_score), 2), ROUND(AVG(CASE WHEN final_score < 60 THEN 1.0 ELSE 0.0 END), 4) FROM score"
    ).fetchone()
    print(f"  avg_score: {avg_score}")
    print(f"  fail_rate: {fail_rate}")

    conn.close()


if __name__ == "__main__":
    main()
