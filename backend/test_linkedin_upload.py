import asyncio
import os
import sys
from app.social.linkedin import LinkedInAuth

async def main():
    if len(sys.argv) < 4:
        print("Usage: python test_linkedin_upload.py <access_token> <person_urn> <file_path>")
        return

    access_token = sys.argv[1]
    person_urn = sys.argv[2]
    file_path = sys.argv[3]

    print(f"Testing LinkedIn Upload for {person_urn}")
    print(f"File: {file_path}")

    auth = LinkedInAuth()
    
    try:
        url = await auth.publish_post(
            access_token=access_token,
            person_urn=person_urn,
            text="Testing Native Upload from local script",
            local_file_path=file_path
        )
        print(f"Success! Post ID: {url}")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
