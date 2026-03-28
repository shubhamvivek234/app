"""
Phase 0.4 — MongoDB Motor async client with explicit pool config.
Never use default pool sizes.
"""
import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None


def get_mongo_settings() -> dict:
    return {
        "maxPoolSize": 50,   # raised from 20 — supports 5 pods × 8 concurrent workers
        "minPoolSize": 10,   # raised from 5
        "maxIdleTimeMS": 30_000,
        "serverSelectionTimeoutMS": 5_000,
        "connectTimeoutMS": 5_000,
        "socketTimeoutMS": 30_000,
    }


async def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        uri = os.environ["MONGODB_URI"]
        _client = AsyncIOMotorClient(uri, **get_mongo_settings())
        # Ping to validate connection
        await _client.admin.command("ping")
        logger.info("MongoDB connection established")
    return _client


async def get_db():
    """FastAPI dependency — yields the default database."""
    client = await get_client()
    db_name = os.environ["DB_NAME"]
    yield client[db_name]


async def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
        logger.info("MongoDB connection closed")
