"""数据库连接、建表、初始化、CRUD 操作。"""

import os
import sqlite3
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional


DEFAULT_SHIFT_ROWS = [
    (1, "早班", "07:30", "13:00"),
    (2, "中班", "13:00", "19:00"),
    (3, "夜班", "19:00", "07:30"),
]

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS Shifts (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS TaskTemplates (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    shift_type INTEGER NOT NULL DEFAULT 0,
    is_active  INTEGER NOT NULL DEFAULT 1,
    due_time   TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS DailyRecords (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id        INTEGER,
    name           TEXT,
    record_date    TEXT NOT NULL,
    shift_type     INTEGER NOT NULL,
    is_completed   INTEGER NOT NULL DEFAULT 0,
    completed_time TEXT,
    is_temp        INTEGER NOT NULL DEFAULT 0,
    due_time       TEXT
);

CREATE INDEX IF NOT EXISTS idx_daily_date_shift ON DailyRecords (record_date, shift_type);
"""


class DatabaseManager:
    """SQLite 数据库管理器，封装所有持久化操作。"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        # RLock 防止跨线程并发访问 SQLite 连接导致状态错乱
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            db_path,
            check_same_thread=False,
            timeout=30.0,  # SQLite 内置忙等：被锁时最多等 30s 而非立即报错
        )
        self._conn.row_factory = sqlite3.Row
        # 关键 PRAGMA：WAL 提升并发 + 防杀毒/同步软件瞬时锁文件导致 database is locked
        self._conn.execute("PRAGMA journal_mode = WAL;")
        self._conn.execute("PRAGMA busy_timeout = 30000;")
        self._conn.execute("PRAGMA synchronous = NORMAL;")
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._init_schema()
        self._seed_default_data()

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.commit()
            except sqlite3.Error:
                pass
            try:
                self._conn.close()
            except sqlite3.Error:
                pass

    # ------- 初始化 -------

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(SCHEMA_SQL)
            self._conn.commit()

    def _seed_default_data(self) -> None:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS c FROM Shifts").fetchone()
            if row["c"] == 0:
                self._conn.executemany(
                    "INSERT INTO Shifts (id, name, start_time, end_time) VALUES (?, ?, ?, ?)",
                    DEFAULT_SHIFT_ROWS,
                )
                self._conn.commit()

    # ------- 班次 Shifts -------

    def get_shifts(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, name, start_time, end_time FROM Shifts ORDER BY id"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_shift(self, shift_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT id, name, start_time, end_time FROM Shifts WHERE id = ?",
                (shift_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_shift(self, shift_id: int, name: str, start_time: str, end_time: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE Shifts SET name = ?, start_time = ?, end_time = ? WHERE id = ?",
                (name, start_time, end_time, shift_id),
            )
            self._conn.commit()

    # ------- 任务模板 TaskTemplates -------

    def list_templates(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, name, shift_type, is_active, due_time, created_at
                FROM TaskTemplates
                ORDER BY shift_type, id
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def list_active_templates_for_shift(self, shift_type: int) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, name, shift_type, is_active, due_time
                FROM TaskTemplates
                WHERE is_active = 1 AND (shift_type = ? OR shift_type = 0)
                ORDER BY id
                """,
                (shift_type,),
            ).fetchall()
        return [dict(r) for r in rows]

    def create_template(
        self, name: str, shift_type: int, is_active: bool, due_time: Optional[str] = None
    ) -> int:
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO TaskTemplates (name, shift_type, is_active, due_time, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name, shift_type, 1 if is_active else 0, due_time, datetime.now().isoformat(timespec="seconds")),
            )
            self._conn.commit()
            return cur.lastrowid

    def update_template(
        self,
        template_id: int,
        name: str,
        shift_type: int,
        is_active: bool,
        due_time: Optional[str] = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE TaskTemplates
                SET name = ?, shift_type = ?, is_active = ?, due_time = ?
                WHERE id = ?
                """,
                (name, shift_type, 1 if is_active else 0, due_time, template_id),
            )
            self._conn.commit()

    def delete_template(self, template_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM TaskTemplates WHERE id = ?", (template_id,))
            self._conn.commit()

    # ------- 每日任务 DailyRecords -------

    def list_records(self, record_date: str, shift_type: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._lock:
            if shift_type is None:
                rows = self._conn.execute(
                    """
                    SELECT id, task_id, name, record_date, shift_type, is_completed,
                           completed_time, is_temp, due_time
                    FROM DailyRecords
                    WHERE record_date = ?
                    ORDER BY id
                    """,
                    (record_date,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT id, task_id, name, record_date, shift_type, is_completed,
                           completed_time, is_temp, due_time
                    FROM DailyRecords
                    WHERE record_date = ? AND shift_type = ?
                    ORDER BY id
                    """,
                    (record_date, shift_type),
                ).fetchall()
        return [dict(r) for r in rows]

    def records_exist(self, record_date: str, shift_type: int) -> bool:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT COUNT(*) AS c FROM DailyRecords
                WHERE record_date = ? AND shift_type = ? AND is_temp = 0
                """,
                (record_date, shift_type),
            ).fetchone()
        return row["c"] > 0

    def generate_daily_from_templates(self, record_date: str, shift_type: int) -> int:
        """为指定日期+班次从模板生成任务记录（增量补齐）。

        - 已存在的 task_id（含已完成的）跳过，保留当天勾选状态
        - 仅插入今天还没生成过的新模板
        - 模板被删除/停用不影响历史记录
        """
        with self._lock:
            templates = self.list_active_templates_for_shift(shift_type)
            if not templates:
                return 0
            existing_rows = self._conn.execute(
                """
                SELECT DISTINCT task_id FROM DailyRecords
                WHERE record_date = ? AND shift_type = ? AND is_temp = 0 AND task_id IS NOT NULL
                """,
                (record_date, shift_type),
            ).fetchall()
            existing_ids = {r["task_id"] for r in existing_rows}
            pending = [t for t in templates if t["id"] not in existing_ids]
            if not pending:
                return 0
            rows = [
                (
                    t["id"],
                    t["name"],
                    record_date,
                    shift_type,
                    0,
                    None,
                    0,
                    t.get("due_time"),
                )
                for t in pending
            ]
            self._conn.executemany(
                """
                INSERT INTO DailyRecords
                    (task_id, name, record_date, shift_type, is_completed,
                     completed_time, is_temp, due_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            self._conn.commit()
            return len(rows)

    def add_temp_task(
        self,
        record_date: str,
        shift_type: int,
        name: str,
        due_time: Optional[str] = None,
    ) -> int:
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO DailyRecords
                    (task_id, name, record_date, shift_type, is_completed,
                     completed_time, is_temp, due_time)
                VALUES (NULL, ?, ?, ?, 0, NULL, 1, ?)
                """,
                (name, record_date, shift_type, due_time),
            )
            self._conn.commit()
            return cur.lastrowid

    def set_record_completed(self, record_id: int, completed: bool) -> None:
        with self._lock:
            if completed:
                ts = datetime.now().isoformat(timespec="seconds")
                self._conn.execute(
                    "UPDATE DailyRecords SET is_completed = 1, completed_time = ? WHERE id = ?",
                    (ts, record_id),
                )
            else:
                self._conn.execute(
                    "UPDATE DailyRecords SET is_completed = 0, completed_time = NULL WHERE id = ?",
                    (record_id,),
                )
            self._conn.commit()

    def delete_record(self, record_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM DailyRecords WHERE id = ?", (record_id,))
            self._conn.commit()
