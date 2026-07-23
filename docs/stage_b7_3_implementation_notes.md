# B.7-3 职工调岗、离职与退休实施说明

完成日期：2026-07-17

## 临时人事确认机制

当前没有独立人事管理员角色，因此人事生命周期事项采用两名不同具名平台管理员的双确认：第一人提交事项并完成密码复验，第二人使用另一账号复验后执行。该机制是演示阶段替代流程，后续应替换为 `personnel_manager` 或权威人事同步。

## 已交付

- 跨学院调动：变更人员学院关系，撤销旧岗位/范围和旧会话，不自动授予新学院角色。
- 离职、退休：结束岗位、撤销业务绑定、归档账号、使登录和旧令牌失效。
- 已领取审核任务返回原队列；教学班和未关闭支持个案建立责任交接异常清单，历史责任不改写。
- 每次确认写入生命周期事件、责任交接、账号历史和审计。

## 接口

- `POST /api/lifecycle/staff/{person_identity_id}/events/{staff_termination|staff_retirement}/request`
- `POST /api/lifecycle/staff/{person_identity_id}/transfer/request`
- `POST /api/lifecycle/staff/events/{event_id}/confirm`

提交及确认均要求 `reason`（确认时保留兼容字段）和 `reauth_password`；调动额外要求 `destination_college_id`。
