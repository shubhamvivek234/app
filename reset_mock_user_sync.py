import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv('backend/.env')

def reset_mock_user():
    print("Connecting to MongoDB (Sync)...")
    client = MongoClient(os.environ['MONGO_URL'])
    db = client[os.environ['DB_NAME']]
    
    email = "findshubhamkumar@gmail.com"
    print(f"Deleting user {email}...")
    result = db.users.delete_one({'email': email})
    
    if result.deleted_count > 0:
        print(f"Successfully deleted user {email}")
    else:
        print(f"User {email} not found (fresh state)")
        
    client.close()

if __name__ == "__main__":
    reset_mock_user()
