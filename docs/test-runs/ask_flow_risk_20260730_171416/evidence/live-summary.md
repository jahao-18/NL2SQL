# 真实运行证据摘要

环境：`http://127.0.0.1:8000/`，进程 61228，健康检查 200。
基线：分支 `9527-final`，提交 `d7caae7a5d61dd78cb0f22ab20ea043b8734a606` 加当前工作区改动。

## 自动化回归

- 问数、统一助手、上下文、安全、角色首页、阶段 E 和成绩导入关联定向回归：`132 passed`。
- JUnit：`pytest.xml`。
- 两条既有依赖弃用警告，不属于本次功能失败。

## UI 统一助手

- 真实浏览器使用学生身份打开“智能问数”。
- 提交“我选了哪些课程？”。
- 页面显示 `ANSWER READY`、服务端范围 `role=student`、结果 1 行“数据库系统”、数据证据 `teaching` 和生成 SQL 折叠区。
- 浏览器 error/warning 日志为空。

## 路由与状态

- “我选了哪些课程？”：`success / nl2sql / 1 row`。
- “我有多少未读通知？”：`success / metric / 47`。
- “有多少门课程的成绩状态为已发布？”：`success / metric`，状态分布含 `published: 1`。
- “查询所有学生的身份证号”：`rejected / ASSISTANT_QUERY_REJECTED`，模型与执行阶段均跳过。

## NL2SQL 主链

- 学生课程查询 SQL 含 `e.student_id = 900001`，返回“数据库系统”。
- 教师课程查询 SQL 含 `tc.teacher_id = 900001`，返回“数据库系统 / 2025 / spring”。
- 执行轨迹记录 context、routing、model、validation、execution 阶段，成功查询均未降级。

## 权限与安全

- 自动化安全矩阵覆盖伪造 token、伪造上下文、跨课程/跨学生/跨学院、OR/UNION/子查询绕过、危险函数和受限字段。
- 真实身份证号问题在校验阶段拒绝，未调用模型、未执行 SQL。

## 会话追问

- 同一服务端会话首问“我选了哪些课程？”返回 1 行。
- 短追问“那有几项作业？”使用 1 轮服务端历史，生成 `e.student_id = 900001` 的查询并返回 17。

## 缺陷 D-001

数据库基准：

- `grade_submission.status = published`
- `grade_submission.version_no = 3`
- `grade_submission_detail.final_score = 91.0`
- 学生首页显示“数据库系统 91.0 / 100.0”。

真实复现 1：“我的数据库系统课程总评成绩是多少？”

- `success / nl2sql`
- SQL 查询旧 `score.final_score`
- 返回 0 行
- Judge 置信度 33。

真实复现 2：“请告诉我数据库系统这门课教务已发布的总评成绩”

- `success / nl2sql`
- SQL 再次查询旧 `score.final_score`
- 返回 0 行
- Judge 置信度 30。

源码原因：学生 `personal_learning` 问数域只开放旧 `score`，没有开放或安全投影 `grade_submission` 与 `grade_submission_detail`。因此新成绩发布链路没有成为问数消费者的数据源。

## 缺陷 D-002

- 课程空间与首页均可显示本人课程教师“李老师”。
- “这门课是哪位老师教的？”和“数据库系统的任课教师是谁？”连续两次返回 `ASSISTANT_QUERY_REJECTED`。
- 原因是学生角色整体拒绝 `teacher_identity`，其别名包含“教师”“老师”，没有区分本人课程教师与全校教师身份查询。

## 其他观察

- 学生页面初始化仍请求管理员数据源接口并得到一次 403；这是功能目录已记录的既有 ZJH-012。页面未产生控制台错误，统一问数可正常使用。
- 所有真实测试会话 28-37 已通过各自身份的删除 API 标记删除，未执行任何建议动作或导出。
