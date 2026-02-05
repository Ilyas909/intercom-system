from fastapi import FastAPI, HTTPException
from app.mqtt_client import start_mqtt_thread
from paho.mqtt.publish import single
from app.db import Session, engine
from app.models import Intercom, Event, SQLModel
from app.mqtt_client import mqtt_client  # нужно будет экспортировать клиент
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

@app.get("/")
def root():
    return {"status": "ok"}


@app.post("/open/{mac}")
def open_door(mac: str, apartment: int | None = None):
    # Проверяем, есть ли домофон
    with Session(engine) as session:
        intercom = session.exec(
            select(Intercom).where(Intercom.mac == mac)
        ).first()
        if not intercom:
            raise HTTPException(status_code=404, detail="Intercom not found")

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


# Добавить после других эндпоинтов
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


@app.post("/api/open/{mac}")
def open_door(mac: str):
    """Открыть дверь через сервер (сценарий от оператора)"""
    try:
        # Публикуем команду в MQTT
        mqtt_client.publish(f"intercom/{mac}/command/open", json.dumps({"source": "operator"}))

        # Сразу создаём событие в БД
        with Session(engine) as session:
            event = Event(
                intercom_mac=mac,
                event_type="door_opened",
                apartment=None,
                payload=json.dumps({"source": "operator", "action": "remote_open"}),
                created_at=datetime.utcnow()
            )
            session.add(event)
            session.commit()

        return {"status": "success", "message": f"Open command sent to {mac}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}