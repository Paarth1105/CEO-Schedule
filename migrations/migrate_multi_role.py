"""Safe, reversible database migration for multi-role scheduling & unique role constraints."""

import argparse
import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from sqlalchemy import inspect, text
from app import app, db
from app.services.schedule_sync import ensure_schema_and_backfill


def upgrade() -> None:
    """Apply multi-role tables, columns, indexes, and safe backfill without data loss."""
    with app.app_context():
        ensure_schema_and_backfill()
        print("Upgrade completed successfully.")


def downgrade() -> None:
    """Safely reverse indexes and new schema objects without deleting existing user/schedule data."""
    with app.app_context():
        inspector = inspect(db.engine)
        drop_indexes = [
            'DROP INDEX IF EXISTS uq_user_active_new_unique_role',
            'DROP INDEX IF EXISTS uq_user_active_admin_proprietor',
            'DROP INDEX IF EXISTS uq_mp_entry_position',
            'DROP INDEX IF EXISTS uq_mp_entry_user',
            'DROP INDEX IF EXISTS ix_schedule_entry_event_date',
            'DROP INDEX IF EXISTS ix_schedule_entry_user_id',
            'DROP INDEX IF EXISTS ix_schedule_entry_status',
            'DROP INDEX IF EXISTS ix_schedule_entry_created_by_id',
        ]
        for stmt in drop_indexes:
            db.session.execute(text(stmt))

        if inspector.has_table('schedule_audit_log'):
            db.session.execute(text('DROP TABLE IF EXISTS schedule_audit_log'))
        if inspector.has_table('meeting_participant'):
            db.session.execute(text('DROP TABLE IF EXISTS meeting_participant'))

        db.session.commit()
        print("Downgrade completed safely (existing user and schedule_entry records preserved).")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Multi-role scheduling DB migration')
    parser.add_argument('action', choices=['upgrade', 'downgrade'], nargs='?', default='upgrade')
    args = parser.parse_args()
    if args.action == 'upgrade':
        upgrade()
    else:
        downgrade()
