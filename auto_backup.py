import os
import shutil
import sqlite3
from datetime import datetime

# 1. Sync live PostgreSQL data into SQLite local cache before backup
try:
    import psycopg2
    pg_conn = psycopg2.connect('postgresql://postgres:Software%402026@127.0.0.1:5432/ceo_schedule')
    pg_cur = pg_conn.cursor()

    sqlite_targets = [
        r'C:\Apps\CEO-Schedule\instance\ceo_schedule.db',
        r'C:\Apps\CEO-Schedule\instance\schedule_app.db',
        r'C:\Apps\CEO-Schedule\ceo_schedule.db'
    ]
    tables = ['user', 'schedule_entry', 'request_message', 'agenda', 'mom', 'notification', 'schedule_attendants']

    for target in sqlite_targets:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        sl_conn = sqlite3.connect(target)
        sl_cur = sl_conn.cursor()
        for table in tables:
            pg_cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}' ORDER BY ordinal_position")
            pg_cols = [c[0] for c in pg_cur.fetchall()]
            if not pg_cols:
                continue

            sl_cur.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
            if not sl_cur.fetchone():
                continue

            sl_cur.execute(f"PRAGMA table_info({table})")
            sl_cols = [c[1] for c in sl_cur.fetchall()]
            common_cols = [c for c in pg_cols if c in sl_cols]
            cols_str = ", ".join([f'"{c}"' for c in common_cols])
            placeholders = ", ".join(["?" for _ in common_cols])

            pg_cur.execute(f'SELECT {cols_str} FROM "{table}"')
            rows = pg_cur.fetchall()
            sl_cur.execute(f'DELETE FROM "{table}"')
            sl_cur.executemany(f'INSERT INTO "{table}" ({cols_str}) VALUES ({placeholders})', rows)
            sl_conn.commit()
        sl_conn.close()
    pg_conn.close()
    print("PostgreSQL to SQLite cache sync successful.")
except Exception as sync_err:
    print(f"Sync warning: {sync_err}")

# 2. Take backup snapshot
source_db = r'C:\Apps\CEO-Schedule\instance\ceo_schedule.db'
if not os.path.exists(source_db):
    source_db = r'C:\Apps\CEO-Schedule\ceo_schedule.db'

backup_dir = r'C:\Apps\CEO-Schedule\Backups'
os.makedirs(backup_dir, exist_ok=True)

timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
target_db = os.path.join(backup_dir, f'ceo_schedule_backup_{timestamp}.sqlite')

try:
    src_conn = sqlite3.connect(source_db)
    dst_conn = sqlite3.connect(target_db)
    with dst_conn:
        src_conn.backup(dst_conn)
    src_conn.close()
    dst_conn.close()
    print(f'SUCCESS: Backup created at {target_db}')
except Exception as e:
    print(f'Backup Failed: {e}')