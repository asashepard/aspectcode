# Should trigger: sec.sql_injection_concat
import sqlite3

def unsafe_query(user_input):
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()
    query = "SELECT * FROM users WHERE name = '" + user_input + "'"
    cursor.execute(query)
    return cursor.fetchall()
