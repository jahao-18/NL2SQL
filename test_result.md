# 测试问题记录

测试问题记录：
1.问题：每个类目销量第一的商品分别是哪个?  
错误：经过 2 次尝试仍失败: no such column: p.name
2.问题：差评最多的五个商品？
错误：结果会输出一个别名的字段 没有显示原来的字段 无法得知数据来源 生成的SQL:SELECT p.name AS product_name, COUNT(*) AS negative_review_count FROM reviews r JOIN products p ON r.product_id = p.id WHERE r.rating = 1 GROUP BY p.id, p.name ORDER BY negative_review_count DESC LIMIT 5
3.问题：分别统计2024/2025/2026三年的订单总金额。 
错误：没有加status=’paid’过滤
生成SQL:SELECT 
    CASE 
        WHEN created_at LIKE '2024%' THEN '2024'
        WHEN created_at LIKE '2025%' THEN '2025'
        WHEN created_at LIKE '2026%' THEN '2026'
    END AS year,
    SUM(amount) AS total_amount
FROM orders
WHERE created_at LIKE '2024%' OR created_at LIKE '2025%' OR created_at LIKE '2026%'
GROUP BY year
ORDER BY year
LIMIT 100
4.问题：去年一共多少订单  错误：输出的是2024的订单 今年是2026 去年应该是2025
5.问题：列出最早注册的1000个用户 错误：只能输出200个 前端没有显示截断信息
6.问题：最贵的用户是谁？ 错误：输出内容为无法回答: users 表中没有价格(price)或消费金额(amount)等可衡量"贵"的字段  
7.问题：（多轮叠加追问）
  （1）2025订单总金额   无错误
   （2）按城市拆分   无错误 SQL：SELECT u.city AS city, SUM(o.amount) AS total_amount FROM orders o JOIN users u ON o.user_id = u.id WHERE o.created_at LIKE '2025%' GROUP BY u.city ORDER BY total_amount DESC LIMIT 100
   （3）只看广东的   错误：有时未把广东省的城市拿出来 结果和第二步一样 三次测试中只有一次成功
   （4）再按月份  错误：如果上一步没成功 这一步也不成功 会莫名的把上海加进来


其他需要注意可能需要改进的问题：
1.输出的结果 显示的字段名是经过对用户问题进行转译的虚拟字段名 不是真实表中的字段名 这使用户无法得知数据来源以及真实性 准确性
2，问题的输入框 输入问题点击查询后 问题自己就没了 不要这样 把用户的问题保留在框中  如果再想查询 用户自己删了框中内容重新打就好了