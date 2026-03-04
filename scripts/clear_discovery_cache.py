import os
import sqlite3

def main():
    # Attempt to locate the database
    db_path = os.getenv("DB_PATH", "data/trunk.db")
    if not os.path.exists(db_path):
        print(f"DB not found at {db_path}")
        return

    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            # Delete any discovery items that haven't been voted on yet
            cursor.execute("DELETE FROM discovery_item WHERE decision IS NULL")
            deleted = cursor.rowcount
            conn.commit()
        print(f"Successfully cleared {deleted} outdated items from the discovery feed cache.")
    except Exception as e:
        print(f"Failed to clear cache: {e}")

if __name__ == "__main__":
    main()
