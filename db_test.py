import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

#only inserts when run directly (python db_test.py), so importing it, e.g. from unittest, can't write to the real database
if __name__ == "__main__":
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        row = conn.execute(
            """INSERT INTO conversations (question, area, psi, answer, tools_used, route)
               VALUES (%s, %s, %s, %s, %s, %s)
               RETURNING id, created_at""",
            ("test question", "west", 156, "test answer", ["get_psi"], "cloud"),
        ).fetchone()
        print("inserted:", row)
