import sqlite3
import os

def migrate():
    db_path = 'nexus.db'
    if not os.path.exists(db_path):
        print(f"Database {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("Checking for Director changes...")
    cursor.execute("PRAGMA table_info(director)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'total_due' not in columns:
        print("Adding total_due to director table...")
        cursor.execute("ALTER TABLE director ADD COLUMN total_due FLOAT DEFAULT 0.0")

    print("Checking for Customer changes...")
    cursor.execute("PRAGMA table_info(customer)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'shares' not in columns:
        print("Adding shares to customer table...")
        cursor.execute("ALTER TABLE customer ADD COLUMN shares FLOAT DEFAULT 0.0")

    print("Checking for Transaction changes...")
    cursor.execute("PRAGMA table_info([transaction])")
    columns = [row[1] for row in cursor.fetchall()]
    if 'customer_installment_id' not in columns:
        print("Adding customer_installment_id to transaction table...")
        cursor.execute("ALTER TABLE [transaction] ADD COLUMN customer_installment_id INTEGER REFERENCES customer_installment(id)")

    print("Creating Installment table if not exists...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS installment (
        id INTEGER PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        amount_per_share FLOAT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    print("Creating CustomerInstallment table if not exists...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS customer_installment (
        id INTEGER PRIMARY KEY,
        customer_id INTEGER NOT NULL REFERENCES customer(id),
        installment_id INTEGER NOT NULL REFERENCES installment(id),
        total_amount FLOAT DEFAULT 0.0,
        paid_amount FLOAT DEFAULT 0.0,
        due_amount FLOAT DEFAULT 0.0
    )
    """)

    conn.commit()
    conn.close()
    print("Migration completed.")

if __name__ == "__main__":
    migrate()
