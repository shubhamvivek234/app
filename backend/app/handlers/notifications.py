from pydantic import BaseModel
from typing import Optional

class GetNotificationsQuery(BaseModel):
    user_id: str
    limit: int = 50

class MarkNotificationReadCommand(BaseModel):
    user_id: str
    notification_id: str

class DeleteNotificationCommand(BaseModel):
    user_id: str
    notification_id: str

async def handle_get_notifications(query: GetNotificationsQuery, db):
    notifications = await db.notifications.find(
        {"user_id": query.user_id}, 
        {"_id": 0}
    ).sort("created_at", -1).limit(query.limit).to_list(query.limit)
    
    # Fix datetime serialization
    from datetime import datetime
    for n in notifications:
        if isinstance(n.get('created_at'), str):
            n['created_at'] = datetime.fromisoformat(n['created_at'])
            
    return notifications

async def handle_mark_read(cmd: MarkNotificationReadCommand, db):
    await db.notifications.update_one(
        {"id": cmd.notification_id, "user_id": cmd.user_id},
        {"$set": {"is_read": True}}
    )
    return {"message": "Marked as read"}

async def handle_delete_notification(cmd: DeleteNotificationCommand, db):
    await db.notifications.delete_one(
        {"id": cmd.notification_id, "user_id": cmd.user_id}
    )
    return {"message": "Notification deleted"}

def register_notification_handlers(bus):
    bus.register(GetNotificationsQuery, handle_get_notifications)
    bus.register(MarkNotificationReadCommand, handle_mark_read)
    bus.register(DeleteNotificationCommand, handle_delete_notification)
