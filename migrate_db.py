import sqlite3
import os

def migrate():
    db_path = r'C:\NRV\nexus.db'
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    migrations = [
        # Table: Director
        "ALTER TABLE director ADD COLUMN coa_account_code VARCHAR(20)",
        
        # Table: Customer
        "ALTER TABLE customer ADD COLUMN coa_account_code VARCHAR(20)",
        
        # Table: Bank
        "ALTER TABLE bank ADD COLUMN coa_account_code VARCHAR(20)",
        
        # Table: Party
        "ALTER TABLE party ADD COLUMN coa_account_code VARCHAR(20)",
        
        # Table: Voucher
        "ALTER TABLE voucher ADD COLUMN debit_account_code VARCHAR(20)",
        "ALTER TABLE voucher ADD COLUMN credit_account_code VARCHAR(20)",
        
        # Table: ContraEntry
        "ALTER TABLE contra_entry ADD COLUMN debit_account_code VARCHAR(20)",
        "ALTER TABLE contra_entry ADD COLUMN credit_account_code VARCHAR(20)",
        
        # Table: Employee
        "ALTER TABLE employee ADD COLUMN coa_account_code VARCHAR(20)",
    ]

    for sql in migrations:
        try:
            print(f"Executing: {sql}")
            cursor.execute(sql)
            print("Success")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print(f"Column already exists, skipping.")
            else:
                print(f"Error: {e}")

    conn.commit()
    conn.close()
    print("Migration completed.")

if __name__ == "__main__":
    migrate()
