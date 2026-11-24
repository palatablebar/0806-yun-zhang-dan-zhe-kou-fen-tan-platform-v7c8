from app.business import decision


def policy(result):
    return decision(result, "ACCOUNT_CAP" if result["flag"] else None)
