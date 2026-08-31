import aiosqlite
from pathlib import Path

class Database:
    def __init__(self, path: Path):
        self.path = path

    async def init(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.executescript('''
            CREATE TABLE IF NOT EXISTS jobs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              url TEXT NOT NULL,
              title TEXT,
              format_id TEXT,
              status TEXT NOT NULL,
              file_path TEXT,
              error TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            ''')
            await db.commit()

    async def create_job(self, user_id: int, url: str) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("INSERT INTO jobs(user_id,url,status) VALUES(?,?,?)", (user_id,url,"queued"))
            await db.commit()
            return cur.lastrowid

    async def update_job(self, job_id: int, **fields):
        if not fields: return
        fields["updated_at"] = "CURRENT_TIMESTAMP"
        assignments=[]; values=[]
        for k,v in fields.items():
            if v == "CURRENT_TIMESTAMP": assignments.append(f"{k}=CURRENT_TIMESTAMP")
            else: assignments.append(f"{k}=?"); values.append(v)
        values.append(job_id)
        async with aiosqlite.connect(self.path) as db:
            await db.execute(f"UPDATE jobs SET {', '.join(assignments)} WHERE id=?", values)
            await db.commit()
