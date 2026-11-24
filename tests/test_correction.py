import io

import pytest
from conftest import csv_data

from app.business import DomainIssue
from app.correction.service import correct, recalculate
from app.review.service import execute, review

BASE = csv_data(
    [
        ["B01", "0001", "pool", "0", "100", "100", "池"],
        ["B02", "0001", "usage", "1", "0", "40", "甲"],
        ["B03", "0001", "usage", "1", "0", "40", "乙"],
        ["B04", "0001", "usage", "1", "0", "40", "丙"],
        ["B05", "0002", "pool", "0", "9", "9", "池"],
        ["B06", "0002", "usage", "2", "0", "6", "丁"],
        ["B07", "0002", "usage", "1", "0", "5", "戊"],
    ]
)
# B03 用量 1→3：共享折扣重新分摊，B02/B04 来源未改但金额变化
REVISED = csv_data(
    [
        ["B01", "0001", "pool", "0", "100", "100", "池"],
        ["B02", "0001", "usage", "1", "0", "40", "甲"],
        ["B03", "0001", "usage", "3", "0", "70", "乙"],
        ["B04", "0001", "usage", "1", "0", "40", "丙"],
        ["B05", "0002", "pool", "0", "9", "9", "池"],
        ["B06", "0002", "usage", "2", "0", "6", "丁"],
        ["B07", "0002", "usage", "1", "0", "5", "戊"],
    ]
)
# 在 REVISED 基础上：0002 池 9→12，B06 用量 2→3
REVISED_AGAIN = csv_data(
    [
        ["B01", "0001", "pool", "0", "100", "100", "池"],
        ["B02", "0001", "usage", "1", "0", "40", "甲"],
        ["B03", "0001", "usage", "3", "0", "70", "乙"],
        ["B04", "0001", "usage", "1", "0", "40", "丙"],
        ["B05", "0002", "pool", "0", "12", "12", "池"],
        ["B06", "0002", "usage", "3", "0", "9", "丁"],
        ["B07", "0002", "usage", "1", "0", "5", "戊"],
    ]
)
OVER_CAP = csv_data(
    [
        ["B01", "0001", "pool", "0", "100", "100", "池"],
        ["B02", "0001", "usage", "1", "0", "40", "甲"],
        ["B03", "0001", "usage", "3", "0", "40", "乙"],
        ["B04", "0001", "usage", "1", "0", "40", "丙"],
        ["B05", "0002", "pool", "0", "9", "9", "池"],
        ["B06", "0002", "usage", "2", "0", "6", "丁"],
        ["B07", "0002", "usage", "1", "0", "5", "戊"],
    ]
)
CONFLICT = csv_data(
    [
        ["B01", "0001", "pool", "0", "100", "100", "池"],
        ["B02", "0001", "usage", "1", "0", "40", "甲"],
        ["B02", "0001", "usage", "2", "0", "40", "甲"],
        ["B03", "0001", "usage", "1", "0", "40", "乙"],
        ["B04", "0001", "usage", "1", "0", "40", "丙"],
        ["B05", "0002", "pool", "0", "9", "9", "池"],
        ["B06", "0002", "usage", "2", "0", "6", "丁"],
        ["B07", "0002", "usage", "1", "0", "5", "戊"],
    ]
)
REMOVED = csv_data(
    [
        ["B01", "0001", "pool", "0", "100", "100", "池"],
        ["B02", "0001", "usage", "1", "0", "60", "甲"],
        ["B03", "0001", "usage", "1", "0", "60", "乙"],
        ["B05", "0002", "pool", "0", "9", "9", "池"],
        ["B06", "0002", "usage", "2", "0", "6", "丁"],
        ["B07", "0002", "usage", "1", "0", "5", "戊"],
    ]
)
ADDED = csv_data(
    [
        ["B01", "0001", "pool", "0", "100", "100", "池"],
        ["B02", "0001", "usage", "1", "0", "40", "甲"],
        ["B03", "0001", "usage", "1", "0", "40", "乙"],
        ["B04", "0001", "usage", "1", "0", "40", "丙"],
        ["B08", "0001", "usage", "1", "0", "40", "新"],
        ["B05", "0002", "pool", "0", "9", "9", "池"],
        ["B06", "0002", "usage", "2", "0", "6", "丁"],
        ["B07", "0002", "usage", "1", "0", "5", "戊"],
    ]
)


@pytest.fixture
def issued(store):
    run = execute(store, BASE)
    return review(store, run["id"], dict(revision=0, status="APPROVED", note="月结已签发"))


def lines_of(result):
    return {line["record"]: line for line in result["report"]["lines"]}


def test_recalculate_full_batch_amounts():
    amounts, _ = recalculate(REVISED)
    assert amounts == {"B02": 20, "B03": 60, "B04": 20, "B06": 6, "B07": 3}


def test_correction_requires_issued_base(store):
    run = execute(store, BASE)
    with pytest.raises(DomainIssue, match="BASE_NOT_ISSUED"):
        correct(store, run["id"], REVISED)
    held = review(store, run["id"], dict(revision=0, status="HELD", note="暂缓待核对"))
    with pytest.raises(DomainIssue, match="BASE_NOT_ISSUED"):
        correct(store, held["id"], REVISED)


def test_correction_missing_base_run(store):
    with pytest.raises(DomainIssue, match="RUN_NOT_FOUND"):
        correct(store, "unknown", REVISED)


def test_changed_accounts_include_unmodified_shared_reallocation(store, issued):
    result = correct(store, issued["id"], REVISED)
    lines = lines_of(result)
    assert set(lines) == {"B02", "B03", "B04"}
    assert (lines["B02"]["before"], lines["B02"]["after"], lines["B02"]["delta"]) == (34, 20, -14)
    assert (lines["B03"]["before"], lines["B03"]["after"], lines["B03"]["delta"]) == (33, 60, 27)
    assert (lines["B04"]["before"], lines["B04"]["after"], lines["B04"]["delta"]) == (33, 20, -13)


def test_unchanged_accounts_generate_no_zero_lines(store, issued):
    result = correct(store, issued["id"], REVISED)
    assert "B06" not in lines_of(result) and "B07" not in lines_of(result)
    assert all(line["delta"] != 0 for line in result["report"]["lines"])


def test_accumulated_matches_latest_full_recalculation(store, issued):
    result = correct(store, issued["id"], REVISED)
    expected, _ = recalculate(REVISED)
    assert result["report"]["accumulated"] == expected


def test_sequential_corrections_accumulate_against_latest_source(store, issued):
    correct(store, issued["id"], REVISED)
    second = correct(store, issued["id"], REVISED_AGAIN)
    lines = lines_of(second)
    assert set(lines) == {"B06"}
    assert (lines["B06"]["before"], lines["B06"]["after"], lines["B06"]["delta"]) == (6, 9, 3)
    expected, _ = recalculate(REVISED_AGAIN)
    assert second["report"]["accumulated"] == expected
    assert len(store.corrections_for(issued["id"])) == 2


def test_same_source_retry_keeps_single_correction_without_double_count(store, issued):
    first = correct(store, issued["id"], REVISED)
    again = correct(store, issued["id"], REVISED)
    assert again["id"] == first["id"] and again == first
    assert len(store.corrections_for(issued["id"])) == 1
    follow = correct(store, issued["id"], REVISED_AGAIN)
    assert follow["report"]["accumulated"] == recalculate(REVISED_AGAIN)[0]
    assert len(store.corrections_for(issued["id"])) == 2


def test_removed_account_is_reversed(store, issued):
    lines = lines_of(correct(store, issued["id"], REMOVED))
    assert (lines["B04"]["before"], lines["B04"]["after"], lines["B04"]["delta"]) == (33, 0, -33)
    assert (lines["B02"]["after"], lines["B03"]["after"]) == (50, 50)


def test_added_account_starts_from_zero(store, issued):
    lines = lines_of(correct(store, issued["id"], ADDED))
    assert (lines["B08"]["before"], lines["B08"]["after"], lines["B08"]["delta"]) == (0, 25, 25)


def test_source_conflict_blocks_entire_correction_with_record_keys(store, issued):
    with pytest.raises(DomainIssue, match="SOURCE_CONFLICT") as failure:
        correct(store, issued["id"], CONFLICT)
    assert failure.value.keys == ["B02"]
    assert store.corrections_for(issued["id"]) == []


def test_over_cap_blocks_entire_correction_with_record_keys(store, issued):
    with pytest.raises(DomainIssue, match="ACCOUNT_CAP") as failure:
        correct(store, issued["id"], OVER_CAP)
    assert failure.value.keys == ["B03"]
    assert store.corrections_for(issued["id"]) == []


def test_no_change_source_creates_no_correction(store, issued):
    with pytest.raises(DomainIssue, match="NO_CHANGES"):
        correct(store, issued["id"], BASE)
    assert store.corrections_for(issued["id"]) == []


def test_original_issuance_evidence_stays_untouched(store, issued):
    before = store.load(issued["id"])
    correct(store, issued["id"], REVISED)
    correct(store, issued["id"], REVISED_AGAIN)
    after = store.load(issued["id"])
    assert after["report"] == before["report"]
    assert (after["revision"], after["status"], after["note"]) == (
        before["revision"],
        before["status"],
        before["note"],
    )


def test_correction_document_identifies_base_and_source(store, issued):
    result = correct(store, issued["id"], REVISED)
    document = result["report"]
    assert document["schema"] == "correction/1" and document["status"] == "ISSUABLE"
    assert document["base"] == {"run_id": issued["id"], "revision": issued["revision"]}
    assert document["summary"]["changed"] == 3
    assert document["summary"]["delta_cents"] == 0  # 组内重新分摊，总额不变
    loaded = store.load_correction(result["id"])
    assert loaded["report"] == document


def approve(client, data):
    run = client.post("/api/runs", data={"file": (io.BytesIO(data), "base.csv")}).json
    return client.patch(
        "/api/runs/" + run["id"],
        json=dict(revision=0, status="APPROVED", note="月结已签发"),
    ).json


def upload(client, run_id, data):
    return client.post(
        f"/api/runs/{run_id}/corrections",
        data={"file": (io.BytesIO(data), "revised.csv")},
    )


def test_http_correction_roundtrip(client):
    run = approve(client, BASE)
    created = upload(client, run["id"], REVISED)
    assert created.status_code == 200
    document = created.json["report"]
    assert {line["record"] for line in document["lines"]} == {"B02", "B03", "B04"}
    retry = upload(client, run["id"], REVISED)
    assert retry.status_code == 200 and retry.json["id"] == created.json["id"]
    listing = client.get(f"/api/runs/{run['id']}/corrections")
    assert listing.status_code == 200 and len(listing.json["items"]) == 1
    fetched = client.get("/api/corrections/" + created.json["id"])
    assert fetched.status_code == 200 and fetched.json["report"] == document


def test_http_correction_blocks(client):
    run = approve(client, BASE)
    conflict = upload(client, run["id"], CONFLICT)
    assert conflict.status_code == 409
    assert conflict.json["code"] == "SOURCE_CONFLICT"
    assert conflict.json["records"] == ["B02"]
    capped = upload(client, run["id"], OVER_CAP)
    assert capped.status_code == 409
    assert capped.json["code"] == "ACCOUNT_CAP"
    assert capped.json["records"] == ["B03"]
    unchanged = upload(client, run["id"], BASE)
    assert unchanged.status_code == 409 and unchanged.json["code"] == "NO_CHANGES"
    assert client.get(f"/api/runs/{run['id']}/corrections").json["items"] == []


def test_http_correction_requires_issued_base(client):
    run = client.post("/api/runs", data={"file": (io.BytesIO(BASE), "base.csv")}).json
    pending = upload(client, run["id"], REVISED)
    assert pending.status_code == 409 and pending.json["code"] == "BASE_NOT_ISSUED"
    assert upload(client, "unknown", REVISED).status_code == 404
    assert client.get("/api/runs/unknown/corrections").status_code == 404
    assert client.get("/api/corrections/unknown").status_code == 404
