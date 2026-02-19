
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv('backend/.env')

async def main():
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'social_scheduler')
    
    print(f"Connecting to {mongo_url}, DB: {db_name}")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    collections = ['users', 'user_sessions', 'social_accounts', 'posts', 'payment_transactions']
    
    for col in collections:
        await db[col].drop()
        print(f"Dropped collection: {col}")
        
    print("\nDatabase reset complete.")
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
