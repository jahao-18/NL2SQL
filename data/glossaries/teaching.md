# Teaching Data Business Glossary

## Business Terms

- 学生人数 = count rows in `student`; by default only include active students with `student.status = 'active'`.
- 在读学生 = `student.status = 'active'`.
- 毕业学生 = `student.status = 'graduated'`.
- 休学学生 = `student.status = 'suspended'`.
- 学院 = `college`.
- 专业 = `major`; a major belongs to a college.
- 班级 = `class_group`; a class group belongs to a major.
- 课程 = `course`; one row means one course.
- 开课班 = `teaching_class`; one row means a course offering in a specific year and semester taught by one teacher.
- 选课人数 = `COUNT(enrollment.id)`.
- 选课学生数 = `COUNT(DISTINCT enrollment.student_id)`.
- 成绩 = `score.final_score`; use final score by default for score analysis.
- 平时成绩 = `score.usual_score`.
- 考试成绩 = `score.exam_score`.
- 绩点 = `score.grade_point`.
- 通过 / 及格 = `score.final_score >= 60` or `score.passed = 1`.
- 未通过 / 不及格 / 挂科 = `score.final_score < 60` or `score.passed = 0`.
- 优秀 = `score.final_score >= 90`.
- 平均分 = `AVG(score.final_score)`.
- 最高分 = `MAX(score.final_score)`.
- 最低分 = `MIN(score.final_score)`.
- 教师授课工作量 = count teaching classes and enrollment records taught by a teacher.
- 教学评价分 = `evaluation.score`, from 1 to 5.
- 评价均分 = `AVG(evaluation.score)`.
- 本学期 = 2025 spring semester: `teaching_class.year = 2025 AND teaching_class.semester = 'spring'`.
- 春季学期 = `semester = 'spring'`.
- 秋季学期 = `semester = 'autumn'`.
- 必修课 = `course.course_type = 'required'`.
- 选修课 = `course.course_type = 'elective'`.
- 通识课 = `course.course_type = 'general'`.
- 性别取值: `male` means 男, `female` means 女.

## Join Rules

- 学生查学院: `student.college_id = college.id`.
- 学生查专业: `student.major_id = major.id`.
- 学生查班级: `student.class_id = class_group.id`.
- 专业查学院: `major.college_id = college.id`.
- 班级查专业: `class_group.major_id = major.id`.
- 教师查学院: `teacher.college_id = college.id`.
- 课程查学院: `course.college_id = college.id`.
- 开课班查课程: `teaching_class.course_id = course.id`.
- 开课班查教师: `teaching_class.teacher_id = teacher.id`.
- 选课查开课班: `enrollment.teaching_class_id = teaching_class.id`.
- 选课查学生: `enrollment.student_id = student.id`.
- 成绩查选课: `score.enrollment_id = enrollment.id`.
- 教学评价查开课班: `evaluation.teaching_class_id = teaching_class.id`.
- 教学评价查学生: `evaluation.student_id = student.id`.

## Derived Metrics

- 平均分 = `AVG(score.final_score)`.
- 及格率 = `AVG(CASE WHEN score.final_score >= 60 THEN 1.0 ELSE 0.0 END)`.
- 挂科率 = `AVG(CASE WHEN score.final_score < 60 THEN 1.0 ELSE 0.0 END)`.
- 优秀率 = `AVG(CASE WHEN score.final_score >= 90 THEN 1.0 ELSE 0.0 END)`.
- 选课人数 = `COUNT(enrollment.id)`.
- 选课学生数 = `COUNT(DISTINCT enrollment.student_id)`.
- 开课数 = `COUNT(teaching_class.id)`.
- 课程数 = `COUNT(course.id)`.
- 教师授课班级数 = `COUNT(DISTINCT teaching_class.id)`.
- 教师授课学生人次 = `COUNT(enrollment.id)`.
- 教学评价均分 = `AVG(evaluation.score)`.
