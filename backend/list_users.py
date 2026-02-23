from motor.motor_asyncio import AsyncIOMotorClient
import os
import asyncio
from dotenv import load_dotenv

async def list_users():
    load_dotenv(override=True)
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = client[os.environ['DB_NAME']]
    users = await db.users.find().to_list(100)
    for u in users:
        print(f"ID: {u.get('user_id')}, Email: {u.get('email')}, Name: {u.get('name')}")

if __name__ == "__main__":
    asyncio.run(list_users())
