from app.business import measured


def compute(data):
    pool, accounts = data
    total = sum(r["usage_units"] for r in accounts)
    shares = [
        (r, *divmod(pool["discount_cents"] * r["usage_units"], total)) for r in accounts
    ]
    extra = pool["discount_cents"] - sum(q for _, q, _ in shares)
    amounts = [
        (r, q + (i < extra))
        for i, (r, q, _) in enumerate(
            sorted(shares, key=lambda x: (-x[2], x[0]["record"]))
        )
    ]
    return measured(
        sum(a for _, a in amounts),
        pool["discount_cents"],
        "分",
        {r["record"]: a for r, a in amounts},
        any(a > r["cap_cents"] for r, a in amounts),
    )
