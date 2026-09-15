"""Database infrastructure for QMRSmithbot."""

# Import runtime models so Alembic and Base.metadata discover every table.
from qmrsmithbot.db import telegram_runtime_models as telegram_runtime_models  # noqa: F401
