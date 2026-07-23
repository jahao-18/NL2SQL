# 阶段 C：通知中心与课程空间实施说明

完成日期：2026-07-17

## 已交付后端能力

- 当前账号通知列表、未读数量与已读标记。
- 教师发布或软删除课程公告；发布时向本课程已选学生生成送达记录和通知，删除时同步撤下对应通知但保留送达记录和审计日志。
- 教师查看公告送达与已读汇总，不读取其他课程成员数据。
- 教师上传课程资料附件或登记外部链接；课程成员读取课程空间中的公告并鉴权下载有效资料。
- 课程空间按教师任课关系或学生选课关系鉴权，并复用既有作业、课程分析接口。

## 接口

- `GET /api/notifications`
- `POST /api/notifications/{notification_id}/read`
- `GET /api/teaching/classes/{teaching_class_id}/space`
- `POST /api/teaching/classes/{teaching_class_id}/announcements`
- `DELETE /api/teaching/announcements/{announcement_id}`
- `GET /api/teaching/announcements/{announcement_id}/receipts`
- `POST /api/teaching/classes/{teaching_class_id}/resources`
- `GET /api/teaching/resources/{resource_id}/file`

## 当前界面边界

教师和学生均已在导航中获得“我的课程”和“通知中心”入口；教师可发布公告并在二次确认后删除，上传课程附件或登记外部资料链接，课程成员可鉴权下载附件，学生可查看课程内容、阅读通知。作业与课程分析仍保留原页面并按课程使用。

课程附件支持 PDF、Word、PowerPoint、Excel、ZIP、常见图片、TXT 和 CSV，单文件不超过 20MB。服务端使用随机存储键落盘且不公开真实路径，每次下载均重新校验教师任课或学生选课关系；外部链接只允许 HTTP(S)。

“我的课程”前端已调整为响应式课程工作台：顶部课程切换，左侧课程概览与业务入口，右侧展示公告、资料及教师发布区；公告和资料入口支持区块定位，移动端自动变为单列布局。
