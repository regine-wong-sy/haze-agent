# Migrations

Numbered SQL files that build the database schema. Run them in order on an empty database to get the same tables as production. To change the schema, add a new file (`002_...sql`) and never edit one that has already been run.

Run one with `psql`:

```bash
psql "$DATABASE_URL" -f migrations/001_create_conversations.sql
```
