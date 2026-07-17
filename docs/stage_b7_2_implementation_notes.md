# B.7-2 学生生命周期实施说明

完成日期：2026-07-17

## 已交付

- 教务处可办理休学、复学、毕业与退学，且具备学生清单和批量毕业能力。
- 休学暂停学生业务身份并保留 `self_service`；复学创建新的当前学生业务绑定。
- 毕业/退学撤销学生业务绑定、归档账号并使旧会话失效，原始业务历史不删除。
- 批量毕业以整批校验和单事务写入执行；一名学生不可办理时不会改动同批其他学生。
- 状态变化记录在 `identity_lifecycle_event`、`account_status_history`（账号归档时）和 `audit_log`。

## 接口

- `GET /api/lifecycle/students?status=active|leave|graduated|withdrawn|all`
- `POST /api/lifecycle/students/{person_identity_id}/student_leave`
- `POST /api/lifecycle/students/{person_identity_id}/student_resume`
- `POST /api/lifecycle/students/{person_identity_id}/student_graduation`
- `POST /api/lifecycle/students/{person_identity_id}/student_withdrawal`
- `POST /api/lifecycle/students/batch-graduation`

单人操作请求体：`{"reason":"学籍变动依据"}`；批量毕业额外传入 `person_identity_ids`，最多 500 人。
