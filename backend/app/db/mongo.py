from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings

mongo_client = AsyncIOMotorClient(settings.mongo_url)
mongo: AsyncIOMotorDatabase = mongo_client[settings.mongo_db]
