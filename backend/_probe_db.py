import sqlite3
conn = sqlite3.connect("data/agent_sessions.db")
for name, sql in conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table'"):
    print("TABLE", name, ":", (sql or "").replace("\n", " ")[:300])
    print("---")
