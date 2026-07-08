# Teaching Data Business Glossary

## Business Terms

- 学生人数 = count rows in `student`; by default only include active students with `student.status = 'active'`.
- 在读学生 = `student.status = 'active'`; 毕业学生 = `student.status = 'graduated'`; 休学学生 = `student.status = 'suspended'`.
- 学院 = `college`; 专业 = `major`; 班级 = `class_group`.
- 课程 = `course`; 开课班 = `teaching_class`, one row means a course offering in a specific year and semester.
- 本学期 = 2025 spring semester: `teaching_class.year = 2025 AND teaching_class.semester = 'spring'`.
- 春季学期 = `semester = 'spring'`; 秋季学期 = `semester = 'autumn'`.
- 必修课 = `course.course_type = 'required'`; 选修课 = `course.course_type = 'elective'`; 通识课 = `course.course_type = 'general'`.
- 成绩 = `score.final_score`; 平时成绩 = `score.usual_score`; 考试成绩 = `score.exam_score`; 绩点 = `score.grade_point`.
- 通过/及格 = `score.final_score >= 60` or `score.passed = 1`; 挂科/未通过 = `score.final_score < 60` or `score.passed = 0`.
- 优秀 = `score.final_score >= 90`; 平均分 = `AVG(score.final_score)`.
- 教学评价分 = `evaluation.score`, from 1 to 5; 评价均分 = `AVG(evaluation.score)`.
- 作业 = `assignment`; 作业提交 = `assignment_submission`; 未提交 = `assignment_submission.status = 'missing'`; 迟交 = `assignment_submission.late = 1`.
- 考勤 = `attendance`; 出勤 = `attendance.status = 'present'`; 迟到 = `attendance.status = 'late'`; 缺勤 = `attendance.status = 'absent'`; 请假 = `attendance.status = 'leave'`.
- 学习行为 = `learning_activity`; 视频学习时长 = `SUM(learning_activity.video_minutes)`; 平台活跃度可结合登录次数、资源浏览、讨论发帖统计。
- 奖助记录 = `scholarship`; 奖助金额 = `scholarship.amount`.
- 学业预警 = `academic_warning`; 风险分 = `academic_warning.risk_score`; 未解除预警 = `academic_warning.resolved = 0`.
- 先修课程 = `course_prerequisite`; a course can require another course as prerequisite.

## Join Rules

- `major.college_id = college.id`.
- `class_group.major_id = major.id`.
- `student.college_id = college.id`; `student.major_id = major.id`; `student.class_id = class_group.id`.
- `teacher.college_id = college.id`; `course.college_id = college.id`.
- `course_prerequisite.course_id = course.id`; `course_prerequisite.prerequisite_course_id = course.id`.
- `teaching_class.course_id = course.id`; `teaching_class.teacher_id = teacher.id`.
- `enrollment.teaching_class_id = teaching_class.id`; `enrollment.student_id = student.id`.
- `score.enrollment_id = enrollment.id`.
- `evaluation.teaching_class_id = teaching_class.id`; `evaluation.student_id = student.id`.
- `assignment.teaching_class_id = teaching_class.id`.
- `assignment_submission.assignment_id = assignment.id`; `assignment_submission.student_id = student.id`.
- `attendance.teaching_class_id = teaching_class.id`; `attendance.student_id = student.id`.
- `learning_activity.teaching_class_id = teaching_class.id`; `learning_activity.student_id = student.id`.
- `scholarship.student_id = student.id`; `academic_warning.student_id = student.id`.

## Derived Metrics

- 选课人次 = `COUNT(enrollment.id)`.
- 选课学生数 = `COUNT(DISTINCT enrollment.student_id)`.
- 平均分 = `AVG(score.final_score)`.
- 及格率 = `AVG(CASE WHEN score.final_score >= 60 THEN 1.0 ELSE 0.0 END)`.
- 挂科率 = `AVG(CASE WHEN score.final_score < 60 THEN 1.0 ELSE 0.0 END)`.
- 优秀率 = `AVG(CASE WHEN score.final_score >= 90 THEN 1.0 ELSE 0.0 END)`.
- 作业提交率 = `AVG(CASE WHEN assignment_submission.status <> 'missing' THEN 1.0 ELSE 0.0 END)`.
- 作业迟交率 = `AVG(CASE WHEN assignment_submission.late = 1 THEN 1.0 ELSE 0.0 END)`.
- 出勤率 = `AVG(CASE WHEN attendance.status = 'present' THEN 1.0 ELSE 0.0 END)`.
- 缺勤率 = `AVG(CASE WHEN attendance.status = 'absent' THEN 1.0 ELSE 0.0 END)`.
- 平均视频学习时长 = `AVG(learning_activity.video_minutes)`.
- 学习活跃度 = `SUM(learning_activity.login_count + learning_activity.resource_views + learning_activity.discussion_posts)`.
- 未解除预警数 = `SUM(CASE WHEN academic_warning.resolved = 0 THEN 1 ELSE 0 END)`.
