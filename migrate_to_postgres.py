import os
import sys
import sqlite3
from sqlalchemy import create_engine, MetaData, Table, text
from sqlalchemy.orm import sessionmaker

def migrate():
    print("=== SQLite to PostgreSQL Migration Tool ===")
    print("Please paste your Render database EXTERNAL Connection URL.")
    print("It should start with 'postgresql://' or 'postgres://'")
    pg_url = input("External Database URL: ").strip()
    if not pg_url:
        print("Error: Database URL is required.")
        return

    # SQLAlchemy requires "postgresql://" protocol (Render sometimes gives "postgres://")
    if pg_url.startswith("postgres://"):
        pg_url = "postgresql://" + pg_url[len("postgres://"):]

    sqlite_db_path = os.path.join("instance", "schedule_app.db")
    if not os.path.exists(sqlite_db_path):
        print(f"Error: Local SQLite database not found at {sqlite_db_path}")
        return

    print("\nConnecting to databases...")
    try:
        # Connect to SQLite
        sqlite_conn = sqlite3.connect(sqlite_db_path)
        sqlite_cursor = sqlite_conn.cursor()

        # Connect to PostgreSQL
        pg_engine = create_engine(pg_url)
        pg_metadata = MetaData()
        pg_metadata.reflect(bind=pg_engine)
        
        # Run db.create_all() on PostgreSQL using Flask app context
        from app import app, db
        with app.app_context():
            app.config['SQLALCHEMY_DATABASE_URI'] = pg_url
            db.create_all()
            print("PostgreSQL tables checked/created successfully.")

        # Re-reflect PostgreSQL tables
        pg_engine = create_engine(pg_url)
        pg_metadata = MetaData()
        pg_metadata.reflect(bind=pg_engine)

        pg_session_factory = sessionmaker(bind=pg_engine)
        pg_session = pg_session_factory()

    except Exception as e:
        print(f"Connection failed: {e}")
        return

    tables_order = ['user', 'schedule_entry', 'request_message', 'notification', 'schedule_attendants']

    print("\nStarting migration...")
    try:
        for table_name in tables_order:
            # Check SQLite table
            sqlite_cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
            if not sqlite_cursor.fetchone():
                print(f"Skipping '{table_name}' (does not exist in SQLite)")
                continue

            # Check PostgreSQL table
            if table_name not in pg_metadata.tables:
                print(f"Error: Table '{table_name}' does not exist in PostgreSQL.")
                continue

            pg_table = pg_metadata.tables[table_name]

            # Fetch rows from SQLite
            sqlite_cursor.execute(f"SELECT * FROM {table_name}")
            rows = sqlite_cursor.fetchall()
            columns = [description[0] for description in sqlite_cursor.description]
            print(f"Migrating table '{table_name}' ({len(rows)} rows)...")

            if not rows:
                continue

            # Truncate existing table to prevent duplicates
            pg_session.execute(text(f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE"))
            pg_session.commit()

            # Insert rows
            for row in rows:
                data = dict(zip(columns, row))
                pg_session.execute(pg_table.insert().values(**data))

            pg_session.commit()
            print(f"Successfully migrated table '{table_name}'")

        # Fix sequence values for auto-increment columns in Postgres
        print("\nUpdating serial sequences...")
        for seq_table in ['user', 'schedule_entry', 'request_message', 'notification']:
            try:
                pg_session.execute(text(f"SELECT setval(pg_get_serial_sequence('{seq_table}', 'id'), COALESCE(MAX(id), 1)) FROM {seq_table}"))
                pg_session.commit()
            except Exception as seq_err:
                print(f"Sequence sync warning on '{seq_table}': {seq_err}")
                pg_session.rollback()

        print("\nMigration completed successfully!")

    except Exception as err:
        pg_session.rollback()
        print(f"\nMigration failed: {err}")
    finally:
        sqlite_conn.close()
        pg_session.close()

if __name__ == "__main__":
    migrate()
