"""Seed a larger teaching-domain SQLite database.

The dataset is deterministic and designed for NL2SQL demos:
- dimension tables for colleges, majors, classes, teachers and courses;
- fact tables for enrollments, scores, evaluations, assignments, attendance,
  learning activity, scholarships and academic warnings;
- enough rows to make aggregation, ranking, cohort, risk and workload queries
  feel realistic without requiring an external database.
"""
from __future__ import annotations

import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "teaching.db"
CURRENT_YEAR = 2025
CURRENT_SEMESTER = "spring"


COLLEGES = [
    (1, "CS", "计算机学院"),
    (2, "MATH", "数学与统计学院"),
    (3, "BUS", "经济管理学院"),
    (4, "ART", "人文与艺术学院"),
    (5, "ENG", "智能工程学院"),
    (6, "MED", "健康科学学院"),
]

MAJORS = [
    (1, 1, "SE", "软件工程"),
    (2, 1, "CS", "计算机科学与技术"),
    (3, 1, "AI", "人工智能"),
    (4, 2, "MATH", "数学与应用数学"),
    (5, 2, "STAT", "统计学"),
    (6, 2, "DS", "数据科学"),
    (7, 3, "ACCT", "会计学"),
    (8, 3, "FIN", "金融学"),
    (9, 3, "MKT", "市场营销"),
    (10, 4, "CHN", "汉语言文学"),
    (11, 4, "DESIGN", "视觉传达设计"),
    (12, 4, "MEDIA", "网络与新媒体"),
    (13, 5, "AUTO", "自动化"),
    (14, 5, "ROBOT", "机器人工程"),
    (15, 5, "IOT", "物联网工程"),
    (16, 6, "NURS", "护理学"),
    (17, 6, "PH", "公共卫生"),
    (18, 6, "REHAB", "康复治疗学"),
]

COURSE_NAMES = {
    1: ["程序设计基础", "数据结构", "数据库系统", "操作系统", "计算机网络", "软件工程", "Web 开发技术", "机器学习基础", "移动应用开发", "信息安全导论", "算法设计", "云计算平台"],
    2: ["高等数学", "线性代数", "概率论与数理统计", "数学分析", "离散数学", "回归分析", "时间序列分析", "运筹学", "随机过程", "统计计算"],
    3: ["管理学原理", "会计学基础", "市场营销", "财务管理", "运营管理", "商业数据分析", "组织行为学", "公司金融", "消费者行为", "供应链管理"],
    4: ["大学语文", "中国文学史", "艺术概论", "新媒体设计", "写作基础", "美学原理", "影视叙事", "版式设计", "文化传播", "数字摄影"],
    5: ["电路原理", "自动控制原理", "机器人导论", "传感器技术", "嵌入式系统", "智能制造", "工业互联网", "数字信号处理", "机械设计基础", "工程实践"],
    6: ["人体解剖学", "护理学基础", "公共卫生导论", "流行病学", "康复评定学", "健康数据分析", "医学统计学", "临床技能训练", "营养与健康", "社区护理"],
}

SURNAMES = list("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜谢邹喻柏水窦章云苏潘葛范彭鲁韦马苗凤花方俞任袁柳鲍史唐费廉岑薛雷贺倪汤")
GIVEN_NAMES = ["一鸣", "子涵", "思源", "雨桐", "梓轩", "嘉怡", "浩然", "明远", "若曦", "欣然", "宇航", "佳宁", "文博", "诗涵", "景行", "知夏", "晨曦", "书瑶", "俊杰", "可欣"]
TITLES = ["助教", "讲师", "副教授", "教授"]
ROOMS = ["A101", "A202", "B305", "C210", "D406", "实验楼301", "实验楼502", "图书馆报告厅", "智慧教室1", "智慧教室2"]
ASSIGNMENT_TYPES = ["homework", "quiz", "project", "lab", "midterm"]
PLATFORMS = ["LMS", "MOOC", "OJ", "实验平台", "课堂互动"]


def make_name() -> str:
    return random.choice(SURNAMES) + random.choice(GIVEN_NAMES)


def clamp(value: float, low: float, high: float, digits: int = 1) -> float:
    return round(max(low, min(high, value)), digits)


def grade_point(final_score: float) -> float:
    if final_score < 60:
        return 0.0
    return round(min(4.0, (final_score - 50.0) / 10.0), 1)


def term_start(year: int, semester: str) -> datetime:
    return datetime(year, 3, 1) if semester == "spring" else datetime(year, 9, 1)


DDL = [
    """CREATE TABLE college (
        id INTEGER PRIMARY KEY, -- 学院ID
        code TEXT NOT NULL UNIQUE, -- 学院编码
        name TEXT NOT NULL -- 学院名称
    )""",
    """CREATE TABLE major (
        id INTEGER PRIMARY KEY, -- 专业ID
        college_id INTEGER NOT NULL, -- 所属学院ID
        code TEXT NOT NULL UNIQUE, -- 专业编码
        name TEXT NOT NULL, -- 专业名称
        FOREIGN KEY (college_id) REFERENCES college(id)
    )""",
    """CREATE TABLE class_group (
        id INTEGER PRIMARY KEY, -- 班级ID
        major_id INTEGER NOT NULL, -- 所属专业ID
        name TEXT NOT NULL, -- 班级名称
        grade_year INTEGER NOT NULL, -- 年级
        FOREIGN KEY (major_id) REFERENCES major(id)
    )""",
    """CREATE TABLE student (
        id INTEGER PRIMARY KEY, -- 学生ID
        student_no TEXT NOT NULL UNIQUE, -- 学号
        name TEXT NOT NULL, -- 学生姓名
        gender TEXT NOT NULL, -- 性别: male/female
        college_id INTEGER NOT NULL, -- 所属学院ID
        major_id INTEGER NOT NULL, -- 所属专业ID
        class_id INTEGER NOT NULL, -- 所属班级ID
        enrollment_year INTEGER NOT NULL, -- 入学年份
        status TEXT NOT NULL, -- 学籍状态: active/graduated/suspended
        FOREIGN KEY (college_id) REFERENCES college(id),
        FOREIGN KEY (major_id) REFERENCES major(id),
        FOREIGN KEY (class_id) REFERENCES class_group(id)
    )""",
    """CREATE TABLE teacher (
        id INTEGER PRIMARY KEY, -- 教师ID
        teacher_no TEXT NOT NULL UNIQUE, -- 工号
        name TEXT NOT NULL, -- 教师姓名
        gender TEXT NOT NULL, -- 性别: male/female
        college_id INTEGER NOT NULL, -- 所属学院ID
        title TEXT NOT NULL, -- 职称
        hire_date TEXT NOT NULL, -- 入职日期
        FOREIGN KEY (college_id) REFERENCES college(id)
    )""",
    """CREATE TABLE course (
        id INTEGER PRIMARY KEY, -- 课程ID
        course_code TEXT NOT NULL UNIQUE, -- 课程编码
        name TEXT NOT NULL, -- 课程名称
        credit REAL NOT NULL, -- 学分
        course_type TEXT NOT NULL, -- 课程类型: required/elective/general
        college_id INTEGER NOT NULL, -- 开课学院ID
        difficulty REAL NOT NULL, -- 难度系数
        FOREIGN KEY (college_id) REFERENCES college(id)
    )""",
    """CREATE TABLE course_prerequisite (
        id INTEGER PRIMARY KEY, -- 先修关系ID
        course_id INTEGER NOT NULL, -- 课程ID
        prerequisite_course_id INTEGER NOT NULL, -- 先修课程ID
        min_score REAL NOT NULL, -- 建议最低先修成绩
        FOREIGN KEY (course_id) REFERENCES course(id),
        FOREIGN KEY (prerequisite_course_id) REFERENCES course(id)
    )""",
    """CREATE TABLE teaching_class (
        id INTEGER PRIMARY KEY, -- 开课班ID
        course_id INTEGER NOT NULL, -- 课程ID
        teacher_id INTEGER NOT NULL, -- 任课教师ID
        year INTEGER NOT NULL, -- 开课年份
        semester TEXT NOT NULL, -- 学期: spring/autumn
        capacity INTEGER NOT NULL, -- 课程容量
        classroom TEXT NOT NULL, -- 教室
        FOREIGN KEY (course_id) REFERENCES course(id),
        FOREIGN KEY (teacher_id) REFERENCES teacher(id)
    )""",
    """CREATE TABLE enrollment (
        id INTEGER PRIMARY KEY, -- 选课ID
        teaching_class_id INTEGER NOT NULL, -- 开课班ID
        student_id INTEGER NOT NULL, -- 学生ID
        enroll_time TEXT NOT NULL, -- 选课时间
        FOREIGN KEY (teaching_class_id) REFERENCES teaching_class(id),
        FOREIGN KEY (student_id) REFERENCES student(id)
    )""",
    """CREATE TABLE score (
        id INTEGER PRIMARY KEY, -- 成绩ID
        enrollment_id INTEGER NOT NULL, -- 选课ID
        usual_score REAL NOT NULL, -- 平时成绩
        exam_score REAL NOT NULL, -- 考试成绩
        final_score REAL NOT NULL, -- 总评成绩
        grade_point REAL NOT NULL, -- 绩点
        passed INTEGER NOT NULL, -- 是否通过: 1=通过,0=未通过
        FOREIGN KEY (enrollment_id) REFERENCES enrollment(id)
    )""",
    """CREATE TABLE evaluation (
        id INTEGER PRIMARY KEY, -- 教学评价ID
        teaching_class_id INTEGER NOT NULL, -- 开课班ID
        student_id INTEGER NOT NULL, -- 学生ID
        score REAL NOT NULL, -- 教学评价分数,1-5
        comment TEXT, -- 评价内容
        FOREIGN KEY (teaching_class_id) REFERENCES teaching_class(id),
        FOREIGN KEY (student_id) REFERENCES student(id)
    )""",
    """CREATE TABLE assignment (
        id INTEGER PRIMARY KEY, -- 作业ID
        teaching_class_id INTEGER NOT NULL, -- 开课班ID
        title TEXT NOT NULL, -- 作业标题
        assignment_type TEXT NOT NULL, -- 作业类型
        publish_time TEXT NOT NULL, -- 发布时间
        due_time TEXT NOT NULL, -- 截止时间
        max_score REAL NOT NULL, -- 满分
        weight REAL NOT NULL, -- 权重
        FOREIGN KEY (teaching_class_id) REFERENCES teaching_class(id)
    )""",
    """CREATE TABLE assignment_submission (
        id INTEGER PRIMARY KEY, -- 提交ID
        assignment_id INTEGER NOT NULL, -- 作业ID
        student_id INTEGER NOT NULL, -- 学生ID
        submit_time TEXT, -- 提交时间
        score REAL, -- 得分
        late INTEGER NOT NULL, -- 是否迟交
        status TEXT NOT NULL, -- 提交状态: submitted/late/missing
        FOREIGN KEY (assignment_id) REFERENCES assignment(id),
        FOREIGN KEY (student_id) REFERENCES student(id)
    )""",
    """CREATE TABLE attendance (
        id INTEGER PRIMARY KEY, -- 考勤ID
        teaching_class_id INTEGER NOT NULL, -- 开课班ID
        student_id INTEGER NOT NULL, -- 学生ID
        session_no INTEGER NOT NULL, -- 第几次课
        class_date TEXT NOT NULL, -- 上课日期
        status TEXT NOT NULL, -- 考勤状态: present/late/absent/leave
        FOREIGN KEY (teaching_class_id) REFERENCES teaching_class(id),
        FOREIGN KEY (student_id) REFERENCES student(id)
    )""",
    """CREATE TABLE learning_activity (
        id INTEGER PRIMARY KEY, -- 学习行为ID
        teaching_class_id INTEGER NOT NULL, -- 开课班ID
        student_id INTEGER NOT NULL, -- 学生ID
        activity_date TEXT NOT NULL, -- 行为日期
        platform TEXT NOT NULL, -- 学习平台
        login_count INTEGER NOT NULL, -- 登录次数
        video_minutes REAL NOT NULL, -- 视频学习分钟数
        resource_views INTEGER NOT NULL, -- 资源浏览次数
        discussion_posts INTEGER NOT NULL, -- 讨论发帖数
        FOREIGN KEY (teaching_class_id) REFERENCES teaching_class(id),
        FOREIGN KEY (student_id) REFERENCES student(id)
    )""",
    """CREATE TABLE scholarship (
        id INTEGER PRIMARY KEY, -- 奖助记录ID
        student_id INTEGER NOT NULL, -- 学生ID
        year INTEGER NOT NULL, -- 年份
        scholarship_type TEXT NOT NULL, -- 奖助类型
        amount REAL NOT NULL, -- 金额
        level TEXT NOT NULL, -- 等级
        FOREIGN KEY (student_id) REFERENCES student(id)
    )""",
    """CREATE TABLE academic_warning (
        id INTEGER PRIMARY KEY, -- 学业预警ID
        student_id INTEGER NOT NULL, -- 学生ID
        year INTEGER NOT NULL, -- 年份
        semester TEXT NOT NULL, -- 学期
        warning_type TEXT NOT NULL, -- 预警类型
        risk_score REAL NOT NULL, -- 风险分
        resolved INTEGER NOT NULL, -- 是否解除
        FOREIGN KEY (student_id) REFERENCES student(id)
    )""",
]

INDEXES = [
    "CREATE INDEX idx_major_college ON major(college_id)",
    "CREATE INDEX idx_class_major ON class_group(major_id)",
    "CREATE INDEX idx_student_college ON student(college_id)",
    "CREATE INDEX idx_student_major ON student(major_id)",
    "CREATE INDEX idx_student_class ON student(class_id)",
    "CREATE INDEX idx_teacher_college ON teacher(college_id)",
    "CREATE INDEX idx_course_college ON course(college_id)",
    "CREATE INDEX idx_prereq_course ON course_prerequisite(course_id)",
    "CREATE INDEX idx_teaching_class_course ON teaching_class(course_id)",
    "CREATE INDEX idx_teaching_class_teacher ON teaching_class(teacher_id)",
    "CREATE INDEX idx_teaching_class_term ON teaching_class(year, semester)",
    "CREATE INDEX idx_enrollment_class ON enrollment(teaching_class_id)",
    "CREATE INDEX idx_enrollment_student ON enrollment(student_id)",
    "CREATE INDEX idx_score_enrollment ON score(enrollment_id)",
    "CREATE INDEX idx_score_final ON score(final_score)",
    "CREATE INDEX idx_evaluation_class ON evaluation(teaching_class_id)",
    "CREATE INDEX idx_assignment_class ON assignment(teaching_class_id)",
    "CREATE INDEX idx_submission_assignment ON assignment_submission(assignment_id)",
    "CREATE INDEX idx_submission_student ON assignment_submission(student_id)",
    "CREATE INDEX idx_attendance_class_student ON attendance(teaching_class_id, student_id)",
    "CREATE INDEX idx_activity_class_student ON learning_activity(teaching_class_id, student_id)",
    "CREATE INDEX idx_scholarship_student ON scholarship(student_id)",
    "CREATE INDEX idx_warning_student_term ON academic_warning(student_id, year, semester)",
]


def generate_classes() -> list[tuple]:
    rows = []
    class_id = 1
    for major_id, _college_id, code, _name in MAJORS:
        for grade_year in range(2021, 2026):
            for idx in range(1, 4):
                rows.append((class_id, major_id, f"{code}{grade_year % 100}{idx:02d}", grade_year))
                class_id += 1
    return rows


def generate_students(classes: list[tuple]) -> list[tuple]:
    major_to_college = {major_id: college_id for major_id, college_id, _code, _name in MAJORS}
    rows = []
    student_id = 1
    for class_id, major_id, _class_name, grade_year in classes:
        college_id = major_to_college[major_id]
        for idx in range(1, random.randint(28, 38) + 1):
            status = random.choices(["active", "graduated", "suspended"], weights=[88, 9, 3])[0]
            rows.append((
                student_id,
                f"{grade_year}{major_id:02d}{class_id:03d}{idx:02d}",
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
        for idx in range(1, 41):
            hire_year = random.randint(2002, 2024)
            rows.append((
                teacher_id,
                f"T{college_id}{idx:03d}",
                make_name(),
                random.choice(["male", "female"]),
                college_id,
                random.choices(TITLES, weights=[10, 44, 31, 15])[0],
                f"{hire_year}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
            ))
            teacher_id += 1
    return rows


def generate_courses() -> list[tuple]:
    rows = []
    course_id = 1
    for college_id, code, _name in COLLEGES:
        for idx, course_name in enumerate(COURSE_NAMES[college_id], start=1):
            course_type = random.choices(["required", "elective", "general"], weights=[52, 34, 14])[0]
            credit = random.choice([1.5, 2.0, 2.5, 3.0, 3.5, 4.0])
            difficulty = clamp(random.gauss(1.0, 0.22), 0.6, 1.55, 2)
            rows.append((course_id, f"{code}{idx:03d}", course_name, credit, course_type, college_id, difficulty))
            course_id += 1
    return rows


def generate_prerequisites(courses: list[tuple]) -> list[tuple]:
    rows = []
    row_id = 1
    by_college: dict[int, list[tuple]] = {}
    for course in courses:
        by_college.setdefault(course[5], []).append(course)
    for group in by_college.values():
        for idx, course in enumerate(group[2:], start=2):
            prereq = random.choice(group[:idx])
            rows.append((row_id, course[0], prereq[0], random.choice([60.0, 65.0, 70.0])))
            row_id += 1
    return rows


def generate_teaching_classes(courses: list[tuple], teachers: list[tuple]) -> list[tuple]:
    rows = []
    row_id = 1
    teachers_by_college: dict[int, list[tuple]] = {}
    for teacher in teachers:
        teachers_by_college.setdefault(teacher[4], []).append(teacher)
    for year in range(2021, 2026):
        for semester in ["spring", "autumn"]:
            for course in courses:
                sections = 2 if course[4] == "required" else random.choice([1, 1, 2])
                for _ in range(sections):
                    teacher = random.choice(teachers_by_college[course[5]])
                    rows.append((
                        row_id,
                        course[0],
                        teacher[0],
                        year,
                        semester,
                        random.choice([45, 60, 80, 100, 120]),
                        random.choice(ROOMS),
                    ))
                    row_id += 1
    return rows


def generate_enrollments(students: list[tuple], courses: list[tuple], teaching_classes: list[tuple]) -> tuple[list[tuple], list[tuple], list[tuple]]:
    course_by_id = {course[0]: course for course in courses}
    classes_by_college: dict[int, list[tuple]] = {}
    current_classes: list[tuple] = []
    for tc in teaching_classes:
        college_id = course_by_id[tc[1]][5]
        classes_by_college.setdefault(college_id, []).append(tc)
        if tc[3] == CURRENT_YEAR and tc[4] == CURRENT_SEMESTER:
            current_classes.append(tc)

    enrollments, scores, evaluations = [], [], []
    enrollment_id = score_id = evaluation_id = 1
    college_bias = {1: 1.0, 2: -1.5, 3: 2.0, 4: 2.8, 5: -0.8, 6: 1.4}
    teacher_quality = {tc[2]: random.uniform(-2.8, 3.2) for tc in teaching_classes}

    for student in students:
        if student[8] != "active":
            continue
        student_id, college_id = student[0], student[4]
        pool = classes_by_college[college_id] + random.sample(current_classes, k=min(18, len(current_classes)))
        selected = random.sample(list({tc[0]: tc for tc in pool}.values()), k=random.randint(8, 13))
        for tc in selected:
            tc_id, course_id, teacher_id, year, semester, _capacity, _room = tc
            start = term_start(year, semester)
            enrollments.append((enrollment_id, tc_id, student_id, (start + timedelta(days=random.randint(0, 20), hours=random.randint(0, 23))).isoformat(timespec="seconds")))
            course = course_by_id[course_id]
            mean = 78.0 + college_bias.get(course[5], 0.0) + teacher_quality[teacher_id] - course[6] * 8.2
            exam = clamp(random.gauss(mean, 11.5), 0, 100)
            usual = clamp(random.gauss(mean + 5.0, 7.0), 0, 100)
            final = clamp(usual * 0.4 + exam * 0.6, 0, 100)
            scores.append((score_id, enrollment_id, usual, exam, final, grade_point(final), 1 if final >= 60 else 0))
            if random.random() < 0.66:
                eval_score = clamp(random.gauss(4.15 + teacher_quality[teacher_id] / 8.0, 0.45), 1, 5)
                evaluations.append((evaluation_id, tc_id, student_id, eval_score, random.choice(["讲解清晰", "案例丰富", "反馈及时", "课程较难", "希望增加实践", "互动较好"])))
                evaluation_id += 1
            enrollment_id += 1
            score_id += 1
    return enrollments, scores, evaluations


def generate_assignments(teaching_classes: list[tuple], enrollments: list[tuple]) -> tuple[list[tuple], list[tuple]]:
    enrollments_by_class: dict[int, list[int]] = {}
    for _eid, tc_id, student_id, _time in enrollments:
        enrollments_by_class.setdefault(tc_id, []).append(student_id)
    assignments, submissions = [], []
    assignment_id = submission_id = 1
    for tc in teaching_classes:
        tc_id, _course_id, _teacher_id, year, semester, _capacity, _room = tc
        if tc_id not in enrollments_by_class:
            continue
        start = term_start(year, semester)
        for idx in range(1, random.randint(3, 5) + 1):
            publish = start + timedelta(days=idx * 18)
            due = publish + timedelta(days=random.choice([7, 10, 14]))
            max_score = random.choice([10.0, 20.0, 100.0])
            assignments.append((assignment_id, tc_id, f"第{idx}次作业", random.choice(ASSIGNMENT_TYPES), publish.date().isoformat(), due.date().isoformat(), max_score, round(random.uniform(0.05, 0.2), 2)))
            for student_id in enrollments_by_class[tc_id]:
                status = random.choices(["submitted", "late", "missing"], weights=[86, 9, 5])[0]
                score = None if status == "missing" else clamp(random.gauss(max_score * 0.82, max_score * 0.16), 0, max_score)
                submit_time = None if status == "missing" else (due + timedelta(days=1 if status == "late" else -random.randint(0, 5), hours=random.randint(0, 23))).isoformat(timespec="seconds")
                submissions.append((submission_id, assignment_id, student_id, submit_time, score, 1 if status == "late" else 0, status))
                submission_id += 1
            assignment_id += 1
    return assignments, submissions


def generate_attendance_activity(teaching_classes: list[tuple], enrollments: list[tuple]) -> tuple[list[tuple], list[tuple]]:
    by_class: dict[int, list[int]] = {}
    for _eid, tc_id, student_id, _time in enrollments:
        by_class.setdefault(tc_id, []).append(student_id)
    attendance, activity = [], []
    att_id = act_id = 1
    for tc in teaching_classes:
        tc_id, _course_id, _teacher_id, year, semester, _capacity, _room = tc
        students = by_class.get(tc_id)
        if not students:
            continue
        start = term_start(year, semester)
        for session in range(1, 7):
            class_date = (start + timedelta(days=session * 7)).date().isoformat()
            for student_id in students:
                status = random.choices(["present", "late", "absent", "leave"], weights=[86, 7, 5, 2])[0]
                attendance.append((att_id, tc_id, student_id, session, class_date, status))
                att_id += 1
        for student_id in students:
            for week in range(1, 5):
                activity.append((
                    act_id,
                    tc_id,
                    student_id,
                    (start + timedelta(days=week * 14 + random.randint(0, 5))).date().isoformat(),
                    random.choice(PLATFORMS),
                    random.randint(1, 18),
                    clamp(random.gauss(95, 42), 0, 300),
                    random.randint(0, 45),
                    random.choices([0, 1, 2, 3, 4, 5], weights=[45, 25, 14, 8, 5, 3])[0],
                ))
                act_id += 1
    return attendance, activity


def generate_student_events(students: list[tuple], scores: list[tuple], enrollments: list[tuple]) -> tuple[list[tuple], list[tuple]]:
    student_scores: dict[int, list[float]] = {}
    enrollment_student = {eid: student_id for eid, _tc, student_id, _time in enrollments}
    for _sid, enrollment_id, _usual, _exam, final, _gp, _passed in scores:
        student_scores.setdefault(enrollment_student[enrollment_id], []).append(final)

    scholarships, warnings = [], []
    scholarship_id = warning_id = 1
    for student in students:
        student_id = student[0]
        vals = student_scores.get(student_id, [])
        avg_score = sum(vals) / len(vals) if vals else 0
        if avg_score >= 78 and random.random() < 0.28:
            scholarships.append((scholarship_id, student_id, CURRENT_YEAR, random.choice(["academic", "innovation", "need_based"]), random.choice([1000.0, 2000.0, 3000.0, 5000.0]), random.choice(["first", "second", "third"])))
            scholarship_id += 1
        fail_count = sum(1 for v in vals if v < 60)
        if fail_count >= 2 or (avg_score and avg_score < 68):
            warnings.append((warning_id, student_id, CURRENT_YEAR, CURRENT_SEMESTER, random.choice(["score_risk", "attendance_risk", "credit_risk"]), clamp(55 + fail_count * 8 + random.random() * 12, 0, 100), random.choice([0, 0, 1])))
            warning_id += 1
    return scholarships, warnings


def main() -> None:
    random.seed(20260708)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON")
    cur.execute("PRAGMA journal_mode = OFF")
    cur.execute("PRAGMA synchronous = OFF")

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
    prereqs = generate_prerequisites(courses)
    cur.executemany("INSERT INTO course_prerequisite VALUES (?, ?, ?, ?)", prereqs)
    teaching_classes = generate_teaching_classes(courses, teachers)
    cur.executemany("INSERT INTO teaching_class VALUES (?, ?, ?, ?, ?, ?, ?)", teaching_classes)
    enrollments, scores, evaluations = generate_enrollments(students, courses, teaching_classes)
    cur.executemany("INSERT INTO enrollment VALUES (?, ?, ?, ?)", enrollments)
    cur.executemany("INSERT INTO score VALUES (?, ?, ?, ?, ?, ?, ?)", scores)
    cur.executemany("INSERT INTO evaluation VALUES (?, ?, ?, ?, ?)", evaluations)
    assignments, submissions = generate_assignments(teaching_classes, enrollments)
    cur.executemany("INSERT INTO assignment VALUES (?, ?, ?, ?, ?, ?, ?, ?)", assignments)
    cur.executemany("INSERT INTO assignment_submission VALUES (?, ?, ?, ?, ?, ?, ?)", submissions)
    attendance, activity = generate_attendance_activity(teaching_classes, enrollments)
    cur.executemany("INSERT INTO attendance VALUES (?, ?, ?, ?, ?, ?)", attendance)
    cur.executemany("INSERT INTO learning_activity VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", activity)
    scholarships, warnings = generate_student_events(students, scores, enrollments)
    cur.executemany("INSERT INTO scholarship VALUES (?, ?, ?, ?, ?, ?)", scholarships)
    cur.executemany("INSERT INTO academic_warning VALUES (?, ?, ?, ?, ?, ?, ?)", warnings)

    for stmt in INDEXES:
        cur.execute(stmt)

    conn.commit()
    tables = [
        "college", "major", "class_group", "student", "teacher", "course", "course_prerequisite",
        "teaching_class", "enrollment", "score", "evaluation", "assignment", "assignment_submission",
        "attendance", "learning_activity", "scholarship", "academic_warning",
    ]
    print(f"OK: seed teaching db -> {DB_PATH}")
    for table in tables:
        print(f"  {table}: {conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]}")
    avg_score, fail_rate = conn.execute(
        "SELECT ROUND(AVG(final_score), 2), ROUND(AVG(CASE WHEN final_score < 60 THEN 1.0 ELSE 0.0 END), 4) FROM score"
    ).fetchone()
    print(f"  avg_score: {avg_score}")
    print(f"  fail_rate: {fail_rate}")
    print(f"  db_size_mb: {DB_PATH.stat().st_size / 1024 / 1024:.1f}")
    conn.close()


if __name__ == "__main__":
    main()
