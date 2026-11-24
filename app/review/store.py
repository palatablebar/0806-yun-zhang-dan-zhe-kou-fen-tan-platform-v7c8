import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from app.business import DomainIssue

SCHEMA = """CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, report TEXT NOT NULL, created TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING', revision INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '', reviewed TEXT
);"""

CORRECTIONS = """CREATE TABLE IF NOT EXISTS corrections (
    id TEXT PRIMARY KEY, base_id TEXT NOT NULL, source_sha256 TEXT NOT NULL,
    report TEXT NOT NULL, created TEXT NOT NULL,
    UNIQUE(base_id, source_sha256)
);"""


class Store:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=15)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute(SCHEMA)
            db.execute(CORRECTIONS)
            yield db

    @contextmanager
    def exclusive(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(
            sqlite3.connect(self.path, timeout=15, isolation_level=None)
        ) as db:
            db.row_factory = sqlite3.Row
            db.execute(SCHEMA)
            db.execute(CORRECTIONS)
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
            except BaseException:
                db.execute("ROLLBACK")
                raise
            else:
                db.execute("COMMIT")

    def register(self, run_id, report):
        with self.connect() as db:
            db.execute(
                "INSERT INTO runs(id,report,created) VALUES (?,?,?) ON CONFLICT(id) DO NOTHING",
                (
                    run_id,
                    json.dumps(report, ensure_ascii=False),
                    report["manifest"]["created"],
                ),
            )
        return self.load(run_id)

    def load(self, run_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise DomainIssue("RUN_NOT_FOUND")
        result = dict(row)
        result["report"] = json.loads(result["report"])
        return result

    def list(self):
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT id,created,status,revision,note FROM runs ORDER BY created DESC,id LIMIT 50"
                )
            ]

    def revise(self, run_id, revision, status, note, now):
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE runs SET status=?,note=?,reviewed=?,revision=revision+1 WHERE id=? AND revision=?",
                (status, note, now, run_id, revision),
            )
            if cursor.rowcount != 1:
                raise DomainIssue("STALE_REVIEW")
        return self.load(run_id)

    @staticmethod
    def correction(row):
        result = dict(row)
        result["report"] = json.loads(result["report"])
        return result

    def find_correction(self, base_id, source_sha256):
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM corrections WHERE base_id=? AND source_sha256=?",
                (base_id, source_sha256),
            ).fetchone()
        return None if row is None else self.correction(row)

    def load_correction(self, correction_id):
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM corrections WHERE id=?", (correction_id,)
            ).fetchone()
        if row is None:
            raise DomainIssue("CORRECTION_NOT_FOUND")
        return self.correction(row)

    def corrections_for(self, base_id):
        with self.connect() as db:
            return [
                self.correction(row)
                for row in db.execute(
                    "SELECT * FROM corrections WHERE base_id=? ORDER BY created,id",
                    (base_id,),
                )
            ]

    def commit_correction(self, correction_id, base_id, source_sha256, created, build):
        """单事务内重检既有更正、叠加历次结果并整份写入，阻断时不留任何行。"""
        with self.exclusive() as db:
            row = db.execute(
                "SELECT * FROM corrections WHERE base_id=? AND source_sha256=?",
                (base_id, source_sha256),
            ).fetchone()
            if row is not None:
                return self.correction(row)
            priors = [
                json.loads(r["report"])
                for r in db.execute(
                    "SELECT report FROM corrections WHERE base_id=? ORDER BY created,id",
                    (base_id,),
                )
            ]
            report = build(priors)
            db.execute(
                "INSERT INTO corrections(id,base_id,source_sha256,report,created) VALUES (?,?,?,?,?)",
                (
                    correction_id,
                    base_id,
                    source_sha256,
                    json.dumps(report, ensure_ascii=False),
                    created,
                ),
            )
        return self.load_correction(correction_id)
