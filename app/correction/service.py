"""更正结算：以最新来源整批重算，对照累计结果生成差额更正行。

规则约定：
- 基准批次必须已签发，原签发证据保持原样；
- 累计（基准 + 历次更正）后的每户折扣必须与最新来源整批重算一致；
- 全量重算后仅纳入金额发生变化的账户，金额未变不生成零额记录；
- 来源冲突、基准未签发或任一户超额度时整份阻断并列出记录键；
- 同一来源重试保留一条有效更正，不得重复累计。
"""

from hashlib import sha256

from app.business import DomainIssue
from app.config import RULE_VERSION
from app.intake.service import inspect
from app.modules.calculate import compute
from app.modules.grouping import case_groups
from app.modules.prepare import prepare
from app.review.service import now


def recalculate(data):
    """整批重算最新来源，返回每户金额与归属分组。

    来源存在隔离行或分组不满足领域约束时按来源冲突阻断；
    任一账户重算金额超过额度时按超额度阻断，均列出记录键。
    """
    intake = inspect(data)
    if intake["rejected"]:
        raise DomainIssue(
            "SOURCE_CONFLICT", sorted({r["record"] for r in intake["isolation"]})
        )
    groups = list(case_groups(intake["rows"]))
    if not groups:
        raise DomainIssue("SOURCE_CONFLICT")
    amounts, homes, over = {}, {}, []
    for case, rows in groups:
        try:
            _, payload = prepare(rows)
        except DomainIssue as error:
            raise DomainIssue(
                "SOURCE_CONFLICT", sorted(r["record"] for r in rows)
            ) from error
        _, accounts = payload
        result = compute(payload)
        for row in accounts:
            amounts[row["record"]] = result["evidence"][row["record"]]
            homes[row["record"]] = case
            if result["evidence"][row["record"]] > row["cap_cents"]:
                over.append(row["record"])
    if over:
        raise DomainIssue("ACCOUNT_CAP", sorted(over))
    return amounts, homes


def baseline_amounts(report):
    """原签发批次每户已签发金额与归属分组。"""
    amounts, homes = {}, {}
    for case in report["cases"]:
        evidence = (case.get("measure") or {}).get("evidence") or {}
        for record, amount in evidence.items():
            amounts[record] = amount
            homes[record] = case["case"]
    return amounts, homes


def accumulate(base_report, priors):
    """基准签发金额叠加历次有效更正后的每户累计金额。"""
    amounts, homes = baseline_amounts(base_report)
    for prior in priors:
        for line in prior["lines"]:
            amounts[line["record"]] = amounts.get(line["record"], 0) + line["delta"]
            homes.setdefault(line["record"], line["case"])
    return amounts, homes


def diff_lines(accumulated, homes, amounts, amount_homes):
    """全量对照：仅保留重算金额发生变化的账户，不生成零额记录。"""
    lines = []
    for record in sorted(set(accumulated) | set(amounts)):
        before = accumulated.get(record, 0)
        after = amounts.get(record, 0)
        if before != after:
            lines.append(
                dict(
                    case=amount_homes.get(record, homes.get(record)),
                    record=record,
                    before=before,
                    after=after,
                    delta=after - before,
                )
            )
    return sorted(lines, key=lambda line: (line["case"], line["record"]))


def correct(store, run_id, data):
    """基于已签发批次形成可签发的更正结算；同一来源重试返回既有更正。"""
    base = store.load(run_id)
    if base["status"] != "APPROVED":
        raise DomainIssue("BASE_NOT_ISSUED")
    fingerprint = sha256(data).hexdigest()
    existing = store.find_correction(run_id, fingerprint)
    if existing is not None:
        return existing
    amounts, homes = recalculate(data)
    correction_id = sha256(
        f"correction:{RULE_VERSION}:{run_id}:{fingerprint}".encode()
    ).hexdigest()
    created = now()

    def build(priors):
        accumulated, accumulated_homes = accumulate(base["report"], priors)
        lines = diff_lines(accumulated, accumulated_homes, amounts, homes)
        if not lines:
            raise DomainIssue("NO_CHANGES")
        return {
            "schema": "correction/1",
            "id": correction_id,
            "version": RULE_VERSION,
            "created": created,
            "status": "ISSUABLE",
            "base": {"run_id": run_id, "revision": base["revision"]},
            "source": {"sha256": fingerprint, "bytes": len(data)},
            "lines": lines,
            "summary": {
                "accounts": len(set(accumulated) | set(amounts)),
                "changed": len(lines),
                "before_cents": sum(line["before"] for line in lines),
                "after_cents": sum(line["after"] for line in lines),
                "delta_cents": sum(line["delta"] for line in lines),
            },
            "accumulated": {record: amounts[record] for record in sorted(amounts)},
        }

    return store.commit_correction(correction_id, run_id, fingerprint, created, build)
