【业务说明 / 取值映射】
- 用户位置有两处:`users.city`(注册时填写)和 `addresses.city / addresses.province`(收货地址)。涉及"省份"必须 JOIN `addresses` 表(`users` 表没有 province)。
- `categories.code` 是英文代号:electronics / clothing / food / book / beauty / sports / home。`categories.name` 是中文名:电子产品 / 服装鞋帽 / 食品饮料 / 图书音像 / 美妆护肤 / 运动户外 / 家居家电。`products` 通过 `category_id` 关联,涉及类目必须 JOIN `categories`。
- 订单状态 `orders.status` 取值:pending / paid / cancelled / refunded(全英文小写)。
- 用户性别 `users.gender` 取值:male / female(全英文小写)。
- `addresses.is_default` 是整数 0 / 1,不是布尔值。
- `created_at` / `registered_at` 是 ISO8601 文本(如 '2025-03-15T10:00:00'),可用 substr/strftime/LIKE 提取年月日。

【派生指标 / 计算口径(用自然语言定义,公式里的概念由你自动匹配到具体字段)】
说明:下列指标不是表里的现成列,而是按公式由现有字段算出来。公式中的概念(如"总消费金额""订单数量")请你自己匹配到最合适的字段/聚合;若公式里某个概念在表中找不到任何对应字段,不要硬凑,按澄清规则向用户说明缺哪个口径。
- 客单价 = 总消费金额 / 订单数量
- 件单价 = 总消费金额 / 总商品件数
