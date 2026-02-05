from sqlmodel import SQLModel, Field
from datetime import datetime


class Intercom(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    mac: str = Field(index=True, unique=True)
    status: str
    door_status: str
    last_seen: datetime = Field(default_factory=datetime.utcnow)


class Event(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    intercom_mac: str = Field(index=True)
    event_type: str  # heartbeat | call | key | open_from_server
    apartment: int | None = None
    payload: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
