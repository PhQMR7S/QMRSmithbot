# Database migrations

Alembic migrations live here. `env.py` loads the application database URL from QMRSmithbot settings, while migration files define the durable PostgreSQL schema.

## Rules

- Every schema change must have an explicit forward and backward migration.
- Models and migrations must be reviewed together; neither is allowed to silently drift.
- Production deployments must run migrations before starting application workers.
- Never commit production database credentials to `alembic.ini` or migration files.
