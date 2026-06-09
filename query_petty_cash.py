import sqlite3
conn = sqlite3.connect(r'C:\NRV\nexus.db')
cursor = conn.cursor()
cursor.execute("SELECT date, type, amount, description FROM petty_cash")
rows = cursor.fetchall()
for r in rows:
    print(r)
