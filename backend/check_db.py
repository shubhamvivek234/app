import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
import json

async def main():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client['social_scheduler']
    
    accounts = await db.social_accounts.find({"user_id": "ZCthsNe1nWTQMygSomMRMtExlQ03"}).to_list(100)
    print("--- SOCIAL ACCOUNTS for ZCthsNe1nWTQMygSomMRMtExlQ03 ---")
    for a in accounts:
        # Remove potentially sensitive or large fields for print
        clean_account = {k:v for k,v in a.items() if k not in ['access_token', 'refresh_token', '_id']}
        print(json.dumps(clean_account, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
