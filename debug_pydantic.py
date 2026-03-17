import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))
from server import Post, PostCreate

# Test if Pydantic drops the accounts array when dumping
post_data = PostCreate(
    content="Test",
    platforms=["youtube"],
    accounts=["acc123"]
)

post = Post(
    user_id="user1",
    content=post_data.content,
    post_type=post_data.post_type,
    platforms=post_data.platforms,
    accounts=post_data.accounts,
    media_urls=post_data.media_urls or []
)

print(post.model_dump())
