from datetime import datetime, timezone
import uuid
from typing import List
from ..bus import bus
from ..models.posts import CreatePostCommand, GetPostsQuery, GetPostQuery, UpdatePostCommand, DeletePostCommand
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

# We need a shared DB instance, ideally injected, but for now we'll import it or pass it.
# We will assume db is passed as an argument to the handler for now, or we can use a global if we must refactor server.py

from typing import List, Optional
    
class Post(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    content: str
    post_type: str = "text"  # text, image, video
    platforms: List[str]
    media_urls: List[str] = []
    video_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    video_title: Optional[str] = None
    scheduled_time: Optional[datetime] = None
    status: str = "draft"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    published_at: Optional[datetime] = None
    ai_generated: bool = False

async def handle_create_post(cmd: CreatePostCommand, db):
    if cmd.scheduled_time and cmd.subscription_status != "active":
        raise HTTPException(status_code=403, detail="Scheduling requires active subscription")
    
    scheduled_time = None
    status = "draft"
    if cmd.scheduled_time:
        scheduled_time = cmd.scheduled_time
        status = "scheduled"
    
    post = Post(
        user_id=cmd.user_id,
        content=cmd.content,
        post_type=cmd.post_type,
        platforms=cmd.platforms,
        media_urls=cmd.media_urls or [],
        video_url=cmd.video_url,
        cover_image_url=cmd.cover_image_url,
        video_title=cmd.video_title,
        scheduled_time=scheduled_time,
        status=status
    )
    
    post_dict = post.model_dump()
    post_dict['created_at'] = post_dict['created_at'].isoformat()
    if post_dict.get('scheduled_time'):
        post_dict['scheduled_time'] = post_dict['scheduled_time'].isoformat()
    
    await db.posts.insert_one(post_dict)
    return post

async def handle_get_posts(query: GetPostsQuery, db):
    q = {"user_id": query.user_id}
    if query.status:
        q["status"] = query.status
    
    posts = await db.posts.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    
    # Fix dates
    for post in posts:
        if isinstance(post.get('created_at'), str):
            post['created_at'] = datetime.fromisoformat(post['created_at'])
        if post.get('scheduled_time') and isinstance(post['scheduled_time'], str):
            post['scheduled_time'] = datetime.fromisoformat(post['scheduled_time'])
        if post.get('published_at') and isinstance(post['published_at'], str):
            post['published_at'] = datetime.fromisoformat(post['published_at'])
            
    return posts

async def handle_get_post(query: GetPostQuery, db):
    post = await db.posts.find_one({"id": query.post_id, "user_id": query.user_id}, {"_id": 0})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    if isinstance(post.get('created_at'), str):
        post['created_at'] = datetime.fromisoformat(post['created_at'])
    if post.get('scheduled_time') and isinstance(post['scheduled_time'], str):
        post['scheduled_time'] = datetime.fromisoformat(post['scheduled_time'])
    if post.get('published_at') and isinstance(post['published_at'], str):
        post['published_at'] = datetime.fromisoformat(post['published_at'])
        
    return Post(**post)

async def handle_update_post(cmd: UpdatePostCommand, db):
    post = await db.posts.find_one({"id": cmd.post_id, "user_id": cmd.user_id})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    update_dict = {k: v for k, v in cmd.model_dump(exclude={'post_id', 'user_id'}, exclude_unset=True).items() if v is not None}
    
    if 'scheduled_time' in update_dict and update_dict['scheduled_time']:
         update_dict['scheduled_time'] = datetime.fromisoformat(update_dict['scheduled_time'].replace('Z', '+00:00')).isoformat()

    if update_dict:
        await db.posts.update_one({"id": cmd.post_id}, {"$set": update_dict})
    
    updated_post = await db.posts.find_one({"id": cmd.post_id}, {"_id": 0})
     
    if isinstance(updated_post.get('created_at'), str):
        updated_post['created_at'] = datetime.fromisoformat(updated_post['created_at'])
    if updated_post.get('scheduled_time') and isinstance(updated_post['scheduled_time'], str):
        updated_post['scheduled_time'] = datetime.fromisoformat(updated_post['scheduled_time'])
    if updated_post.get('published_at') and isinstance(updated_post['published_at'], str):
        updated_post['published_at'] = datetime.fromisoformat(updated_post['published_at'])
            
    return Post(**updated_post)

async def handle_delete_post(cmd: DeletePostCommand, db):
    result = await db.posts.delete_one({"id": cmd.post_id, "user_id": cmd.user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"message": "Post deleted"}

def register_post_handlers():
    bus.register(CreatePostCommand, handle_create_post)
    bus.register(GetPostsQuery, handle_get_posts)
    bus.register(GetPostQuery, handle_get_post)
    bus.register(UpdatePostCommand, handle_update_post)
    bus.register(DeletePostCommand, handle_delete_post)
