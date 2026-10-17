import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    row = conn.execute(
        """INSERT INTO conversations (question, area, psi, answer, tools_used, route)
           VALUES (%s, %s, %s, %s, %s, %s)
           RETURNING id, created_at""",
        ("test question", "west", 156, "test answer", ["get_psi"], "cloud"),
    ).fetchone()
    print("inserted:", row)