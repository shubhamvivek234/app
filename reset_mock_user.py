import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv('backend/.env')

async def reset_mock_user():
    print("Connecting to MongoDB...")
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = client[os.environ['DB_NAME']]
    
    email = "findshubhamkumar@gmail.com"
    print(f"Deleting user {email}...")
    result = await db.users.delete_one({'email': email})
    
    if result.deleted_count > 0:
        print(f"Successfully deleted user {email}")
    else:
        print(f"User {email} not found (fresh state)")
        
    client.close()

if __name__ == "__main__":
    asyncio.run(reset_mock_user())
