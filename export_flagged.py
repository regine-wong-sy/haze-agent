"""Turn flagged conversations into eval test-case skeletons.

Run:  python export_flagged.py
Then paste the ones you want into TESTS in eval.py and fill in the words the
corrected answer must (or must not) contain."""
import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    rows = conn.execute(
        """SELECT id, question, psi, answer FROM conversations
           WHERE flagged ORDER BY created_at"""
    ).fetchall()

print(f"#{len(rows)} flagged conversations\n")
for id, question, psi, answer in rows:
    print(f"#conversation {id}, the answer that was flagged:")
    print("#  " + answer.replace("\n", "\n#  "))
    print(f'{{"psi": {psi}, "question": {question!r},')
    print('     "must_include": [], "must_not_include": []},\n')
