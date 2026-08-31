import aiosqlite
from pathlib import Path


class Database:
    def __init__(self, path: Path):
        self.path = path

    async def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  chat_id INTEGER NOT NULL,
                  message_id INTEGER,
                  url TEXT NOT NULL,
                  title TEXT,
                  format_id TEXT,
                  status TEXT NOT NULL,
                  file_path TEXT,
                  storage_key TEXT,
                  download_url TEXT,
                  error TEXT,
                  attempts INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id);
                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
                CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at);
            """)
            await db.commit()

    async def create_job(self, user_id: int, chat_id: int, url: str, status: str = "pending") -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "INSERT INTO jobs(user_id,chat_id,url,status) VALUES(?,?,?,?)",
                (user_id, chat_id, url, status),
            )
            await db.commit()
            return int(cur.lastrowid)

    async def get_job(self, job_id: int):
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM jobs WHERE id=?", (job_id,))
            return await cur.fetchone()

    async def update_job(self, job_id: int, **fields) -> None:
        if not fields:
            return
        fields["updated_at"] = "CURRENT_TIMESTAMP"
        allowed = {"chat_id", "message_id", "title", "format_id", "status",
                   "file_path", "storage_key", "download_url", "error",
                   "attempts", "updated_at"}
        assignments, values = [], []
        for key, value in fields.items():
            if key not in allowed:
                raise ValueError(f"Unsupported job field: {key}")
            if value == "CURRENT_TIMESTAMP":
                assignments.append(f"{key}=CURRENT_TIMESTAMP")
            else:
                assignments.append(f"{key}=?")
                values.append(value)
        values.append(job_id)
        async with aiosqlite.connect(self.path) as db:
            await db.execute(f"UPDATE jobs SET {', '.join(assignments)} WHERE id=?", values)
            await db.commit()

    async def list_active_jobs(self):
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM jobs WHERE status IN ('queued','downloading','uploading') ORDER BY id"
            )
            return await cur.fetchall()

    async def count_user_active_jobs(self, user_id: int) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT COUNT(*) FROM jobs WHERE user_id=? AND status IN ('queued','downloading','uploading')",
                (user_id,),
            )
            row = await cur.fetchone()
            return int(row[0])
