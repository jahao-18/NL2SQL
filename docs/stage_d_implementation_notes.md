# 阶段 D：考勤与课程答疑实施说明

完成日期：2026-07-17

质量基线：全量自动化测试 `120 passed`。

## 已交付能力

- 新增 `course_session`，记录教学班、课次、日期、起止时间、教室、主题和状态。
- 旧 `attendance` 记录在启动迁移中关联真实课程场次；新增记录同时保留兼容字段并写入 `course_session_id`。
- 任课教师建立本人课程场次，按实际选课名单批量登记出勤、迟到、请假和缺勤。
- 教师可以再次保存修正考勤；首次登记和后续修正使用不同审计动作保留历史痕迹。
- 学生只查看本人场次和考勤；辅导员只查看所带学生必要事实，不获得教师备注、课程名单或其他学生数据。
- 学生在本人课程发起公开或私密问题；私密问题只对提问学生和任课教师可见。
- 教师回复、关闭、重新打开和置顶问题；学生可以追问，答疑状态按 `open -> answered -> closed` 流转。
- 新问题通知任课教师，教师回复通知提问学生，学生追问再次通知教师。
- 新增响应式“课程考勤”和“课程答疑”页面，并从“我的课程”提供业务入口。

## 接口

- `GET/POST /api/teaching/classes/{teaching_class_id}/sessions`
- `GET/PUT /api/teaching/sessions/{session_id}/attendance`
- `GET /api/teaching/attendance/students/{student_id}`
- `GET/POST /api/teaching/classes/{teaching_class_id}/questions`
- `GET/PATCH /api/teaching/questions/{question_id}`
- `POST /api/teaching/questions/{question_id}/replies`

## 权限边界

- 教师不能创建或登记其他教师课程的场次和考勤。
- 学生不能登记考勤、读取他人考勤或读取他人的私密问题。
- 公开问题在学生端不返回提问者学号和内部学生 ID。
- 辅导员必须通过行政班负责关系访问考勤事实，接口不返回考勤备注和答疑内容。
- 已关闭问题不能继续回复；考勤状态和问题状态均由后端白名单校验。
