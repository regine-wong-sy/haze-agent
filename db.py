import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

def save_conversation(question, info):
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute(
            """INSERT INTO conversations (question, area, psi, answer, tools_used, route)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (question, info["area"], info["psi"], info["answer"], info["tools_used"], info["route"]),
        )