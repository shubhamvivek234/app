import asyncio
import os
import json
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv('backend/.env')

async def main():
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'social_scheduler')
    
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    # 1. First get user ID
    user_doc = await db.users.find_one({"email": "findshubhamkumar@gmail.com"})
    if not user_doc:
        print("User not found")
        return
        
    uid = user_doc["user_id"]
    print(f"User ID: {uid}")
    
    # 2. Get Social Accounts
    cursor = db.social_accounts.find({"user_id": uid}, {"_id": 0})
    accounts = await cursor.to_list(length=100)
    
    print(f"\nFound {len(accounts)} connected accounts:")
    print(json.dumps(accounts, indent=2, default=str))

    client.close()

if __name__ == "__main__":
    asyncio.run(main())
