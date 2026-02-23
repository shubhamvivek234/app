from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
import os
from dotenv import load_dotenv

load_dotenv('backend/.env')

async def main():
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = client[os.environ['DB_NAME']]
    accounts = await db.social_accounts.find().to_list(100)
    for acc in accounts:
        print(acc)
    client.close()

if __name__ == '__main__':
    asyncio.run(main())
