from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from threading import Barrier

from app.business import DomainIssue
from app.review.service import execute, review


def test_parallel_rerun_commits_single_row(store, clean):
    start = Barrier(4)

    def load():
        start.wait(3)
        return execute(store, clean)

    with ThreadPoolExecutor(max_workers=4) as threads:
        results = list(threads.map(lambda _: load(), range(4)))
    assert all(result == results[0] for result in results)
    assert len(store.list()) == 1


def test_parallel_review_has_one_winner(store, dirty):
    run = execute(store, dirty)
    start = Barrier(2)

    def attempt(note):
        start.wait(3)
        try:
            return review(store, run["id"], dict(revision=0, status="HELD", note=note))[
                "status"
            ]
        except DomainIssue as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as threads:
        results = list(threads.map(attempt, ["来源待检查", "分组待处理"]))
    assert sorted(results) == ["HELD", "STALE_REVIEW"]
    assert store.load(run["id"])["revision"] == 1


def test_parallel_correction_retry_commits_single_row(store):
    from app.correction.service import correct
    from test_correction import BASE, REVISED

    run = execute(store, BASE)
    review(store, run["id"], dict(revision=0, status="APPROVED", note="月结已签发"))
    start = Barrier(4)

    def load():
        start.wait(3)
        return correct(store, run["id"], REVISED)

    with ThreadPoolExecutor(max_workers=4) as threads:
        results = list(threads.map(lambda _: load(), range(4)))
    assert all(result["id"] == results[0]["id"] for result in results)
    assert len(store.corrections_for(run["id"])) == 1


def test_parallel_distinct_sources_accumulate_in_order(store):
    from app.correction.service import correct, recalculate
    from test_correction import BASE, REVISED, REVISED_AGAIN

    run = execute(store, BASE)
    review(store, run["id"], dict(revision=0, status="APPROVED", note="月结已签发"))
    start = Barrier(2)

    def load(data):
        start.wait(3)
        return correct(store, run["id"], data)

    with ThreadPoolExecutor(max_workers=2) as threads:
        results = list(threads.map(load, [REVISED, REVISED_AGAIN]))
    assert {result["report"]["source"]["sha256"] for result in results} == {
        sha256(REVISED).hexdigest(),
        sha256(REVISED_AGAIN).hexdigest(),
    }
    # 无论哪份先入账，累计结果都必须等于最新来源整批重算
    final = correct(store, run["id"], REVISED_AGAIN)
    assert final["report"]["accumulated"] == recalculate(REVISED_AGAIN)[0]
    assert len(store.corrections_for(run["id"])) == 2
