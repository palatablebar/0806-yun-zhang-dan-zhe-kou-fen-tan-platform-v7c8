from app.business import DomainIssue, by_kind, prepared, single


def prepare(rows):
    pool = single(rows, "pool")
    accounts = [r for r in by_kind(rows, "usage") if r["usage_units"]]
    if not accounts:
        raise DomainIssue("NO_ELIGIBLE_USAGE")
    return prepared(
        len(accounts),
        {"units": sum(r["usage_units"] for r in accounts)},
        (pool, accounts),
    )
