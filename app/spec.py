COLUMNS = ("usage_units", "discount_cents", "cap_cents")
KINDS = ("usage", "pool")
PROJECT = {
    "name": "云账单折扣分摊台",
    "actor": "云财务月结专员",
    "stages": [
        ("intake", "样例采信"),
        ("prepare", "用量归集"),
        ("calculate", "折扣分摊"),
        ("policy", "额度复核"),
        ("balance", "运行对账"),
    ],
    "chart": "对账金额",
}
