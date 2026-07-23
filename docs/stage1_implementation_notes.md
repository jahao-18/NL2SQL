# 阶段 1 开发说明

本阶段完成“底座改造与访问控制”的最小可验收版本，目标是先让业务 API 的数据范围不可绕过，再继续做作业闭环。

## 已完成内容

- 新增 `app/core/teaching_migrations.py`：可重复创建 MVP 业务表，并写入确定性演示账号、课程、作业、提交、辅导员带班关系和学习支持事项。
- 新增 `app/core/authorization.py`：集中实现服务层授权校验，包括 `require_course_member`、`require_teacher_of_class`、`require_counselor_of_student`、`require_submission_access`、`require_support_case_access`。
- 新增 `app/api/teaching.py`：提供阶段 1 验收用教学业务 API，用于验证学生、教师、辅导员的数据范围。
- 更新 `app/main.py`：应用启动时执行可重复迁移，并注册教学业务路由。
- 更新 `app/core/business_domains.py`：加入辅导员角色和 MVP 多账号；教师分析权限不再包含 `academic_warning`；令牌加入过期时间；改密后使用 PBKDF2 哈希存储，同时兼容旧明文默认密码。
- 更新 `scripts/seed_teaching_db.py`：重建教学数据库后自动补齐 MVP 演示范围数据。

## 阶段 1 验收点

- `stu_zhang` 只能访问本人课程和本人提交，访问 `stu_wang` 的提交返回 `403`。
- `tea_li` 只能访问 `数据库系统-1班` 的提交列表，访问 `Web 开发技术-1班` 返回 `403`。
- `counselor_chen` 只能访问所带班级的学习支持事项，`counselor_lin` 或教师访问该事项返回 `403`。
- 教师角色的 NL2SQL 允许表中不再包含 `academic_warning`。
- 业务 API 统一从登录上下文推导身份范围，不信任前端传入的学生、教师或辅导员 ID。

## 下一阶段入口

阶段 2 应在现有授权层之上实现作业发布、学生提交、退回重交、评分和成绩发布。所有写操作需要复用本阶段的授权函数，并写入 `audit_log`。
