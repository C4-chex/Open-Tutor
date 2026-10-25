"""Verify SQLite WAL mode and pragma configuration."""

import asyncio
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url


def test_sqlite_wal_configured():
    """WAL mode should be enabled when using SQLite."""
    from database import engine, is_sqlite

    if not is_sqlite():
        pytest.skip("Not using SQLite")

    async def _check():
        async with engine.connect() as conn:
            result = await conn.execute(text("PRAGMA journal_mode"))
            mode = result.scalar()
            assert mode == "wal", f"Expected WAL mode, got {mode}"

            result = await conn.execute(text("PRAGMA foreign_keys"))
            fk = result.scalar()
            assert fk == 1, "foreign_keys should be ON"

    asyncio.run(_check())


@pytest.mark.asyncio
async def test_file_database_transactions_do_not_roll_back_other_sessions():
    """Overlapping requests must not share one SQLite transaction."""
    from database import engine, is_sqlite

    if not is_sqlite() or make_url(str(engine.url)).database in (None, "", ":memory:"):
        pytest.skip("Requires a file-backed SQLite database")

    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE IF NOT EXISTS test_transaction_isolation (value INTEGER)"))
        await conn.execute(text("DELETE FROM test_transaction_isolation"))
    try:
        async with engine.connect() as writer, engine.connect() as reader:
            await writer.execute(text("INSERT INTO test_transaction_isolation VALUES (42)"))
            await reader.execute(text("SELECT 1"))
            await reader.rollback()
            await writer.commit()

        async with engine.connect() as conn:
            values = (await conn.execute(text("SELECT value FROM test_transaction_isolation"))).scalars().all()
        assert values == [42]
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE test_transaction_isolation"))
