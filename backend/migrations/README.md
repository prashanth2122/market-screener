# Migrations

Alembic migration framework for backend schema evolution.

## Commands

From repo root:

```powershell
python -m alembic -c .\backend\alembic.ini upgrade head
python -m alembic -c .\backend\alembic.ini downgrade -1
python -m alembic -c .\backend\alembic.ini revision -m "describe_change"
```

For autogenerate (after models are added):

```powershell
python -m alembic -c .\backend\alembic.ini revision --autogenerate -m "add_tables"
```
