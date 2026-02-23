import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv('backend/.env')

async def main():
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'social_scheduler')
    
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    # Update social_accounts schema mismatches
    print("Running migration for social_accounts...")
    
    # 1. Rename username -> platform_username
    result1 = await db.social_accounts.update_many(
        {"username": {"$exists": True}},
        {"$rename": {"username": "platform_username"}}
    )
    print(f"Renamed 'username' to 'platform_username' in {result1.modified_count} docs.")
    
    # 2. Rename token_expires_at -> token_expiry
    result2 = await db.social_accounts.update_many(
        {"token_expires_at": {"$exists": True}},
        {"$rename": {"token_expires_at": "token_expiry"}}
    )
    print(f"Renamed 'token_expires_at' to 'token_expiry' in {result2.modified_count} docs.")

    client.close()

if __name__ == "__main__":
    asyncio.run(main())
