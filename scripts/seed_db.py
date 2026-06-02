"""生成示例电商数据库 data/app.db。

规模:1000 用户 / 7 类目 / ~170 商品 / 30000 订单 / ~9000 评价 / ~1500 地址。
6 张表,多 FK 关系,用于测试 LLM 多表 JOIN 推理边界。

关键 schema 变化:products.category 改为 category_id FK,LLM 必须 JOIN
categories 才能按类目筛选 —— 这是有意为之的测试点。
"""
from __future__ import annotations

import random
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "app.db"

DDL = [
    """
    CREATE TABLE categories (
        id          INTEGER PRIMARY KEY,           -- 类目ID
        code        TEXT    NOT NULL UNIQUE,       -- 英文代号: electronics/clothing/food/book/beauty/sports/home
        name        TEXT    NOT NULL,              -- 类目中文名称
        description TEXT                           -- 类目描述
    )
    """,
    """
    CREATE TABLE users (
        id            INTEGER PRIMARY KEY,         -- 用户ID
        name          TEXT    NOT NULL,            -- 用户姓名
        gender        TEXT    NOT NULL,            -- 性别: male / female
        age           INTEGER NOT NULL,            -- 年龄
        city          TEXT    NOT NULL,            -- 所在城市
        registered_at TEXT    NOT NULL             -- 注册时间(ISO8601)
    )
    """,
    """
    CREATE TABLE products (
        id          INTEGER PRIMARY KEY,           -- 商品ID
        name        TEXT    NOT NULL,              -- 商品名称
        category_id INTEGER NOT NULL,              -- 类目ID(关联 categories.id)
        price       REAL    NOT NULL,              -- 商品单价(元)
        stock       INTEGER NOT NULL,              -- 当前库存
        FOREIGN KEY (category_id) REFERENCES categories(id)
    )
    """,
    """
    CREATE TABLE orders (
        id         INTEGER PRIMARY KEY,            -- 订单ID
        user_id    INTEGER NOT NULL,               -- 下单用户ID(关联 users.id)
        product_id INTEGER NOT NULL,               -- 购买商品ID(关联 products.id)
        quantity   INTEGER NOT NULL,               -- 购买数量
        amount     REAL    NOT NULL,               -- 订单金额(元,= quantity * price)
        status     TEXT    NOT NULL,               -- 订单状态: pending/paid/cancelled/refunded
        created_at TEXT    NOT NULL,               -- 下单时间(ISO8601)
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    )
    """,
    """
    CREATE TABLE reviews (
        id         INTEGER PRIMARY KEY,            -- 评价ID
        order_id   INTEGER NOT NULL,               -- 关联订单ID(关联 orders.id)
        user_id    INTEGER NOT NULL,               -- 评价用户ID(关联 users.id)
        product_id INTEGER NOT NULL,               -- 评价商品ID(关联 products.id)
        rating     INTEGER NOT NULL,               -- 评分: 1-5 星
        comment    TEXT,                           -- 评价文本内容(可为空表示仅打星不写评论)
        created_at TEXT    NOT NULL,               -- 评价时间(ISO8601)
        FOREIGN KEY (order_id) REFERENCES orders(id),
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    )
    """,
    """
    CREATE TABLE addresses (
        id         INTEGER PRIMARY KEY,            -- 地址ID
        user_id    INTEGER NOT NULL,               -- 用户ID(关联 users.id)
        province   TEXT    NOT NULL,               -- 省份
        city       TEXT    NOT NULL,               -- 城市
        detail     TEXT    NOT NULL,               -- 街道详细地址
        is_default INTEGER NOT NULL DEFAULT 0,     -- 是否默认收货地址: 0=否 1=是
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """,
]

INDEXES = [
    "CREATE INDEX idx_orders_user ON orders(user_id)",
    "CREATE INDEX idx_orders_product ON orders(product_id)",
    "CREATE INDEX idx_orders_status ON orders(status)",
    "CREATE INDEX idx_orders_created_at ON orders(created_at)",
    "CREATE INDEX idx_reviews_product ON reviews(product_id)",
    "CREATE INDEX idx_reviews_user ON reviews(user_id)",
    "CREATE INDEX idx_products_category ON products(category_id)",
    "CREATE INDEX idx_addresses_user ON addresses(user_id)",
]

# (id, code, name_cn, description)
CATEGORIES = [
    (1, "electronics", "电子产品", "手机/电脑/数码/家电类电子产品"),
    (2, "clothing",    "服装鞋帽", "男女装、鞋类、配饰"),
    (3, "food",        "食品饮料", "零食、酒水、生鲜、烘焙"),
    (4, "book",        "图书音像", "技术、文学、商业、儿童读物"),
    (5, "beauty",      "美妆护肤", "护肤、彩妆、香水、个护"),
    (6, "sports",      "运动户外", "健身器材、运动装备、户外用品"),
    (7, "home",        "家居家电", "厨房电器、家具、收纳"),
]

SURNAMES = [
    "张","王","李","赵","刘","陈","杨","黄","吴","周",
    "徐","孙","胡","朱","高","林","何","郭","马","罗",
    "梁","宋","郑","谢","韩","唐","冯","于","董","程",
    "曹","袁","邓","许","傅","沈","曾","彭","吕","苏",
    "卢","蒋","蔡","贾","丁","魏","薛","叶","姚","汪",
]
GIVEN_M = [
    "伟","强","磊","勇","军","洋","刚","明","超","华",
    "建","志","涛","鹏","峰","宇","晨","浩","凯","斌",
    "飞","龙","辉","文","杰","旭","轩","俊","博","帅","坤",
]
GIVEN_F = [
    "芳","娜","静","丽","婷","秀","英","敏","雪","梅",
    "艳","燕","蕾","蓉","颖","洁","瑶","晶","慧","倩",
    "琳","悦","欣","雯","馨","佳","茜","雅",
]

CITIES = [
    "北京","上海","广州","深圳","杭州","成都","武汉","南京","西安","重庆",
    "天津","苏州","青岛","长沙","厦门","郑州","济南","合肥","昆明","沈阳",
    "哈尔滨","福州","宁波","无锡","佛山","东莞","大连","南昌","太原","石家庄",
]

PROVINCES: dict[str, str] = {
    "北京": "北京", "上海": "上海", "广州": "广东", "深圳": "广东", "佛山": "广东", "东莞": "广东",
    "杭州": "浙江", "宁波": "浙江", "成都": "四川", "武汉": "湖北", "南京": "江苏", "苏州": "江苏", "无锡": "江苏",
    "西安": "陕西", "重庆": "重庆", "天津": "天津", "青岛": "山东", "济南": "山东",
    "长沙": "湖南", "厦门": "福建", "福州": "福建", "郑州": "河南", "合肥": "安徽",
    "昆明": "云南", "沈阳": "辽宁", "大连": "辽宁", "哈尔滨": "黑龙江",
    "南昌": "江西", "太原": "山西", "石家庄": "河北",
}

# 各类目下的 (商品名, 单价) 列表
PRODUCTS_BY_CAT: dict[str, list[tuple[str, float]]] = {
    "electronics": [
        ("iPhone 13", 5499), ("iPhone 14", 6199), ("iPhone 15", 6999), ("iPhone 15 Pro", 8999), ("iPhone 16", 7499),
        ("MacBook Air M2", 7999), ("MacBook Air M3", 9499), ("MacBook Pro 14 M3", 14999),
        ("iPad mini 7", 4299), ("iPad Air 11", 4799), ("iPad Pro 12.9", 9499),
        ("AirPods 4", 1099), ("AirPods Pro 2", 1899), ("AirPods Max", 4399),
        ("Apple Watch S9", 3299), ("Apple Watch Ultra 2", 6499),
        ("Sony WH-1000XM5", 2799), ("Bose QC Ultra", 2999),
        ("华为 Mate 60", 6499), ("华为 Mate X5", 12999),
        ("小米 14", 3999), ("小米手环 9", 249),
        ("Nintendo Switch OLED", 2099), ("PS5 数字版", 3499), ("Xbox Series X", 3899),
        ("Kindle Paperwhite", 1099), ("Dyson V12 吸尘器", 4290),
        ("索尼 ZV-1 相机", 4899), ("华硕 ROG 笔记本", 12999), ("戴尔 XPS 15", 13999),
    ],
    "clothing": [
        ("Nike Pegasus 40 跑鞋", 699), ("Nike Air Force 1", 899),
        ("Adidas Ultra Boost", 1299), ("Adidas Stan Smith", 599), ("Adidas 三叶草卫衣", 499),
        ("New Balance 990v6", 1599), ("Asics GEL Kayano", 1199), ("Vans Old Skool", 449),
        ("优衣库纯棉 T 恤", 99), ("优衣库 Heattech 保暖衣", 199),
        ("Zara 修身衬衫", 299), ("H&M 牛仔裤", 199),
        ("Levi's 511 牛仔裤", 599), ("Levi's Trucker 夹克", 799),
        ("北面 Denali 抓绒", 1199), ("北面冲锋衣 Antora", 1599), ("哥伦比亚 Whirlibird", 1799),
        ("波司登羽绒服男款", 899), ("波司登羽绒服女款", 999),
        ("耐克 Tech Fleece 套装", 999), ("Champion 卫衣", 399),
        ("Polo Ralph Lauren 衬衫", 899), ("Lacoste Polo 衫", 799),
        ("Burberry 风衣", 12999), ("Coach 男士单肩包", 2999), ("MK 女士手提包", 1999),
        ("New Era 棒球帽", 199), ("Patagonia 抓绒帽", 99),
    ],
    "food": [
        ("三只松鼠坚果礼盒", 129), ("百草味零食大礼包", 99), ("良品铺子年货礼盒", 199),
        ("茅台飞天 500ml", 2599), ("五粮液第八代", 1099), ("剑南春水晶剑", 359),
        ("可口可乐 24听整箱", 89), ("百事可乐 24听整箱", 79),
        ("农夫山泉 24瓶", 49), ("元气森林无糖", 79),
        ("蒙牛纯牛奶 12盒", 59), ("伊利金典有机奶", 69), ("特仑苏纯牛奶", 75),
        ("哈根达斯桶装", 79), ("八喜冰淇淋", 49),
        ("好利来榴莲千层", 168), ("稻香村月饼礼盒", 199), ("中粮粽子礼盒", 149),
        ("奥利奥饼干家庭装", 39), ("乐事薯片家庭装", 19),
        ("瑞士莲巧克力礼盒", 299), ("德芙巧克力", 49),
        ("褚橙礼盒 5kg", 199), ("阳光玫瑰葡萄 3kg", 99),
        ("十月稻田东北大米 5kg", 59), ("金龙鱼食用油 5L", 89),
    ],
    "book": [
        ("《Python 编程从入门到实践》", 79), ("《流畅的 Python 第二版》", 159),
        ("《设计模式》", 89), ("《算法导论》", 128), ("《代码大全》", 109),
        ("《重构 改善既有代码》", 99), ("《深入理解计算机系统》", 139),
        ("《人工智能 现代方法》", 159),
        ("《活着》", 35), ("《许三观卖血记》", 32),
        ("《三体》全集", 99), ("《球状闪电》", 39),
        ("《白夜行》", 45), ("《嫌疑人 X 的献身》", 39),
        ("《追风筝的人》", 39), ("《百年孤独》", 49), ("《1984》", 39),
        ("《房思琪的初恋乐园》", 45),
        ("《被讨厌的勇气》", 39), ("《非暴力沟通》", 39),
        ("《纳瓦尔宝典》", 69), ("《原则》", 99),
        ("《人类简史》", 69), ("《未来简史》", 69),
    ],
    "beauty": [
        ("兰蔻小黑瓶精华 50ml", 1380), ("兰蔻菁纯系列面霜", 1980),
        ("雅诗兰黛小棕瓶 50ml", 950), ("雅诗兰黛口红 #420", 320), ("雅诗兰黛 DW 粉底液", 460),
        ("SK-II 神仙水 230ml", 1590), ("SK-II 大红瓶面霜", 1599),
        ("资生堂红妍系列精华", 1280), ("资生堂洗面奶", 220),
        ("欧莱雅复颜系列眼霜", 280), ("欧莱雅紫熨斗", 399),
        ("迪奥蓝星香水", 999), ("香奈儿 5 号香水", 1199),
        ("YSL 莹亮唇釉", 320), ("MAC 子弹头口红", 220),
        ("纪梵希明星散粉", 480), ("阿玛尼大师粉底液", 720),
        ("赫莲娜绿宝瓶精华", 2980), ("La Mer 海蓝之谜面霜", 3950), ("CPB 隔离霜", 950),
        ("珂润润浸保湿乳液", 199), ("城野医生收敛水", 159),
    ],
    "sports": [
        ("瑜伽垫加厚 8mm", 89), ("瑜伽球 65cm", 69),
        ("跳绳负重款", 49),
        ("哑铃 10kg 一对", 199), ("哑铃 20kg 一对", 359),
        ("壶铃 16kg", 199), ("阻力带套装", 79),
        ("筋膜枪按摩仪", 399),
        ("智能跑步机 X1", 2999), ("椭圆机 E5", 3499), ("动感单车 S22", 2299),
        ("羽毛球拍 YONEX", 599), ("乒乓球拍蝴蝶", 1299), ("网球拍 Wilson Pro", 1599),
        ("滑雪板 Burton", 4999),
        ("公路自行车 Giant", 5999), ("山地车 Trek", 6999),
        ("冲浪板 9 尺", 2999),
        ("帐篷 3-4 人", 599), ("睡袋户外保暖", 299),
    ],
    "home": [
        ("戴森吹风机 HD15", 2999), ("戴森无绳吸尘器 V12", 4290),
        ("飞利浦电动剃须刀", 599), ("松下纳米水离子吹风", 1699),
        ("美的电饭煲 4L", 399), ("苏泊尔电压力锅", 499),
        ("九阳豆浆机", 299), ("摩飞早餐机", 599),
        ("德龙咖啡机 ECAM", 5499), ("Nespresso 胶囊机", 1599),
        ("小米空气净化器 Pro H", 1999), ("352 空气净化器 X83", 3499),
        ("夏普加湿器 750ml", 899), ("小熊电热水壶", 159),
        ("惠而浦洗衣机 10kg", 2999), ("海尔三门冰箱", 3999),
        ("方太燃气灶嵌入式", 2999), ("老板抽油烟机", 3999),
        ("林氏木业沙发三人位", 4999), ("顾家床垫 1.8m", 3999),
        ("宜家书桌", 599),
    ],
}

REVIEW_POS = [
    "非常满意,推荐购买", "物流很快,产品质量不错", "性价比很高",
    "和描述一致,会回购", "用了一周,体验很好", "颜值在线,功能也好用",
    "包装很精美,送人也合适", "做工扎实,物有所值",
]
REVIEW_MID = [
    "一般般,凑合用", "有点小瑕疵但不影响使用",
    "价格偏贵,效果还行", "和预期有差距", "无功无过",
]
REVIEW_NEG = [
    "质量太差,已退货", "和描述严重不符",
    "用了几天就坏了", "客服态度不好", "完全不值这个价",
]

STREETS = ["中山路", "人民路", "解放路", "建设路", "和平路", "南京路", "淮海路", "长安街", "西湖大道", "高新大道"]


def random_iso_datetime(year: int) -> str:
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    hour = random.randint(0, 23)
    minute = random.randint(0, 59)
    return f"{year}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00"


def generate_users(n: int) -> list[tuple]:
    out = []
    for i in range(1, n + 1):
        gender = random.choice(["male", "female"])
        surname = random.choice(SURNAMES)
        given_pool = GIVEN_M if gender == "male" else GIVEN_F
        given = random.choice(given_pool)
        if random.random() < 0.65:
            given += random.choice(GIVEN_M + GIVEN_F)
        name = surname + given
        age = random.randint(18, 75)
        city = random.choice(CITIES)
        reg_year = random.choices([2020, 2021, 2022, 2023, 2024], weights=[5, 10, 20, 30, 35])[0]
        out.append((i, name, gender, age, city, random_iso_datetime(reg_year)))
    return out


def generate_products() -> list[tuple]:
    out = []
    pid = 1
    cat_code_to_id = {c[1]: c[0] for c in CATEGORIES}
    for code, items in PRODUCTS_BY_CAT.items():
        cat_id = cat_code_to_id[code]
        for name, price in items:
            stock = random.randint(0, 500)  # 含 0 库存,便于"缺货"类查询
            out.append((pid, name, cat_id, float(price), stock))
            pid += 1
    return out


def generate_orders(n_users: int, products: list[tuple], n: int) -> list[tuple]:
    out = []
    status_pool = ["paid"] * 65 + ["pending"] * 15 + ["cancelled"] * 15 + ["refunded"] * 5
    qty_choices = [1, 2, 3, 4, 5]
    qty_weights = [55, 25, 10, 6, 4]
    year_choices = [2024, 2025, 2026]
    year_weights = [30, 50, 20]
    for oid in range(1, n + 1):
        uid = random.randint(1, n_users)
        prod = random.choice(products)
        pid, _name, _cat, price, _stock = prod
        qty = random.choices(qty_choices, weights=qty_weights)[0]
        amount = round(qty * price, 2)
        status = random.choice(status_pool)
        year = random.choices(year_choices, weights=year_weights)[0]
        out.append((oid, uid, pid, qty, amount, status, random_iso_datetime(year)))
    return out


def generate_reviews(orders: list[tuple], review_rate: float = 0.3) -> list[tuple]:
    out = []
    rid = 1
    for o in orders:
        if o[5] != "paid":
            continue
        if random.random() > review_rate:
            continue
        oid, uid, pid = o[0], o[1], o[2]
        rating = random.choices([5, 4, 3, 2, 1], weights=[50, 25, 15, 7, 3])[0]
        if rating >= 4:
            comment = random.choice(REVIEW_POS)
        elif rating == 3:
            comment = random.choice(REVIEW_MID)
        else:
            comment = random.choice(REVIEW_NEG)
        if random.random() < 0.15:
            comment = None  # 15% 仅打星不写评论
        year = int(o[6][:4])
        out.append((rid, oid, uid, pid, rating, comment, random_iso_datetime(year)))
        rid += 1
    return out


def generate_addresses(n_users: int) -> list[tuple]:
    out = []
    aid = 1
    for uid in range(1, n_users + 1):
        n_addr = random.choices([1, 2, 3], weights=[60, 30, 10])[0]
        for k in range(n_addr):
            city = random.choice(CITIES)
            province = PROVINCES.get(city, city)
            detail = f"{random.choice(STREETS)}{random.randint(1, 9999)}号"
            is_default = 1 if k == 0 else 0
            out.append((aid, uid, province, city, detail, is_default))
            aid += 1
    return out


def main() -> None:
    random.seed(42)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    for stmt in DDL:
        cur.execute(stmt)

    cur.executemany("INSERT INTO categories VALUES (?, ?, ?, ?)", CATEGORIES)

    users = generate_users(1000)
    cur.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)", users)

    products = generate_products()
    cur.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?)", products)

    orders = generate_orders(len(users), products, 30000)
    cur.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?)", orders)

    reviews = generate_reviews(orders, review_rate=0.3)
    cur.executemany("INSERT INTO reviews VALUES (?, ?, ?, ?, ?, ?, ?)", reviews)

    addresses = generate_addresses(len(users))
    cur.executemany("INSERT INTO addresses VALUES (?, ?, ?, ?, ?, ?)", addresses)

    for idx_sql in INDEXES:
        cur.execute(idx_sql)

    conn.commit()

    print(f"OK: seed db -> {DB_PATH}")
    for tbl in ["categories", "users", "products", "orders", "reviews", "addresses"]:
        cnt = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        print(f"  {tbl}: {cnt}")

    status_dist = dict(conn.execute(
        "SELECT status, COUNT(*) FROM orders GROUP BY status ORDER BY 2 DESC"
    ).fetchall())
    rating_dist = dict(conn.execute(
        "SELECT rating, COUNT(*) FROM reviews GROUP BY rating ORDER BY 1 DESC"
    ).fetchall())
    print(f"  orders.status: {status_dist}")
    print(f"  reviews.rating: {rating_dist}")

    conn.close()


if __name__ == "__main__":
    main()
