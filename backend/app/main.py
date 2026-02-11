from fastapi import FastAPI, HTTPException
from app.mqtt_client import mqtt_client, start_mqtt_thread
from paho.mqtt.publish import single
from app.db import Session, engine
from app.models import Intercom, Event, SQLModel
from datetime import datetime
import json
import os
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request
from sqlmodel import select

templates = Jinja2Templates(directory="app/templates")

MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")

app = FastAPI()

@app.on_event("startup")
def on_startup():
    start_mqtt_thread()


@app.post("/open/{mac}")
def open_door(mac: str, apartment: int | None = None):
    # Проверяем, есть ли домофон
    with Session(engine) as session:
        intercom = session.exec(
            select(Intercom).where(Intercom.mac == mac)
        ).first()
        if not intercom:
            raise HTTPException(status_code=404, detail="Intercom not found")
        if intercom.status != "online":
            raise HTTPException(status_code=400, detail="Intercom is offline")

        # Отправляем команду в MQTT
        topic = f"intercom/{mac}/cmd"
        payload = json.dumps({"action": "open", "apartment": apartment})
        single(topic, payload, hostname=MQTT_HOST)

        # Сохраняем событие на сервере (команда)
        event = Event(
            intercom_mac=mac,
            event_type="open_command",
            apartment=apartment,
            payload=payload,
            created_at=datetime.utcnow()
        )
        session.add(event)
        session.commit()
    return {"status": "ok", "mac": mac}



@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    with Session(engine) as session:
        intercoms = session.exec(select(Intercom)).all()
    return templates.TemplateResponse("dashboard.html", {"request": request, "intercoms": intercoms})

@app.get("/api/intercoms")
def api_intercoms():
    with Session(engine) as session:
        intercoms = session.exec(select(Intercom)).all()
    return intercoms


@app.get("/api/events")
def get_events(mac: str | None = None, limit: int = 50):
    """Получить последние события (фильтр по MAC опционален)"""
    with Session(engine) as session:
        query = select(Event).order_by(Event.created_at.desc())
        if mac:
            query = query.where(Event.intercom_mac == mac)
        query = query.limit(limit)
        events = session.exec(query).all()

        return [
            {
                "id": e.id,
                "intercom_mac": e.intercom_mac,
                "event_type": e.event_type,
                "apartment": e.apartment or "-",
                "payload": json.loads(e.payload),
                "created_at": e.created_at.isoformat()
            }
            for e in events
        ]
