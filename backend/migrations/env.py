from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.models.base import Base
import app.models  # noqa: F401 - Register all SQLAlchemy models

config = context.config

# Configure logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Read the database URL from the existing Pydantic settings.
database_url = str(settings.database_url)

# Escape percent signs for ConfigParser.
config.set_main_option(
    "sqlalchemy.url",
    database_url.replace("%", "%%"),
)

# Register all SQLAlchemy models for autogeneration.
target_metadata = Base.metadata


def include_object(object_, name, type_, reflected, compare_to):
    """Do not let Alembic manage tables owned by Supabase Auth."""
    if type_ == "table" and getattr(object_, "info", {}).get("external_table"):
        return False
    return True


def run_migrations_offline() -> None:
    """Generate migration SQL without a live database connection."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_schemas=False,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the configured database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
                include_schemas=False,
                include_object=include_object,
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
