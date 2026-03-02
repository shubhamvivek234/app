import os
import firebase_admin
from firebase_admin import credentials, storage
import json

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
cred = credentials.Certificate(os.path.join(ROOT_DIR, 'serviceAccountKey.json'))

project_id = "socialentangler-b92a8"
bucket_name = f"{project_id}.firebasestorage.app"

print(f"Testing bucket: {bucket_name}")

try:
    firebase_admin.initialize_app(cred, {
        'storageBucket': bucket_name
    })
    bucket = storage.bucket()
    
    # Create simple text file in memory
    blob = bucket.blob("test_firebase_upload.txt")
    blob.upload_from_string("testing firebase storage")
    blob.make_public()
    
    print(f"Success! Public URL: {blob.public_url}")
except Exception as e:
    print(f"Error: {e}")
