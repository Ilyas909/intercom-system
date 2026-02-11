import json
import threading
import time
from datetime import datetime, timedelta
from paho.mqtt.client import Client
from app.db import engine
from app.models import Intercom, Event
from sqlmodel import Session, select

BROKER = "mosquitto"
_check_thread = None


def handle_message(topic: str, payload: dict):
    """Обрабатывает все типы событий от домофона"""
    try:
        parts = topic.split("/")
        if len(parts) < 3 or parts[0] != "intercom":
            print(f"Invalid topic format: {topic}")
            return

        mac = parts[1]
        event_type = parts[2]
        if event_type == "cmd" or event_type == "door_closed":
            return

        with Session(engine) as session:
            # Получаем или создаём домофон
            intercom = session.exec(
                select(Intercom).where(Intercom.mac == mac)
            ).first()

            if not intercom:
                intercom = Intercom(
                    mac=mac,
                    status="online",
                    door_status="closed",
                    last_seen=datetime.utcnow()
                )
                session.add(intercom)
                session.commit()
                session.refresh(intercom)
                print(f"✓ New intercom registered: {mac}")

            # Обновляем last_seen и статус
            intercom.last_seen = datetime.utcnow()
            intercom.status = "online"

            # Обрабатываем тип события
            if event_type == "heartbeat":
                intercom.door_status = payload.get("door_status", "unknown")
                print(f"Heartbeat from {mac}: door={intercom.door_status}")

            elif event_type == "call":
                apartment = payload.get("apartment", "N/A")
                print(f"Call from {mac} to apartment {apartment}")

            elif event_type == "key":
                apartment = payload.get("apartment", "N/A")
                key_id = payload.get("key_id", "unknown")
                print(f"Key used at {mac}: apartment={apartment}, key_id={key_id}")

            elif event_type == "door_opened":
                intercom.door_status = "open"
                source = payload.get("source", "unknown")
                print(f"Door opened at {mac} (source: {source})")
                # Автоматически закроем дверь через 5 секунд (симуляция)
                threading.Timer(5.0, lambda: _auto_close_door(mac)).start()

            # Сохраняем событие в БД
            event = Event(
                intercom_mac=mac,
                event_type=event_type,
                apartment=payload.get("apartment"),
                payload=json.dumps(payload),
                created_at=datetime.utcnow()
            )
            session.add(event)
            session.commit()

    except Exception as e:
        print(f"❌ Error in handle_message: {e}")
        import traceback
        traceback.print_exc()


def _auto_close_door(mac: str):
    """Автоматически закрывает дверь через 5 секунд (симуляция реального поведения)"""
    try:
        with Session(engine) as session:
            intercom = session.exec(
                select(Intercom).where(Intercom.mac == mac)
            ).first()
            if intercom and intercom.door_status == "open":
                intercom.door_status = "closed"
                session.commit()
                print(f"Door auto-closed at {mac}")
    except Exception as e:
        print(f"Error in _auto_close_door: {e}")


def check_inactive_intercoms():
    """Проверяет неактивные домофоны каждые 30 сек"""
    while True:
        try:
            with Session(engine) as session:
                cutoff = datetime.utcnow() - timedelta(minutes=2)
                inactive = session.exec(
                    select(Intercom).where(
                        Intercom.last_seen < cutoff,
                        Intercom.status == "online"
                    )
                ).all()

                for intercom in inactive:
                    intercom.status = "offline"
                    print(f"⚠️  Intercom {intercom.mac} marked offline (last seen: {intercom.last_seen})")

                if inactive:
                    session.commit()
        except Exception as e:
            print(f"Error in check_inactive_intercoms: {e}")

        time.sleep(30)


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        print(f"MQTT {msg.topic}: {payload}")
        handle_message(msg.topic, payload)
    except Exception as e:
        print(f"❌ Error parsing MQTT message: {e}")


def start_mqtt():
    client = Client()
    client.on_message = on_message
    client.connect(BROKER, 1883, 60)
    client.subscribe("intercom/+/+")
    print("Connected to MQTT broker, subscribed to 'intercom/+/+'")
    client.loop_forever()


def start_mqtt_thread():
    """Запускает все фоновые потоки"""
    # Поток для проверки неактивных домофонов
    global _check_thread
    _check_thread = threading.Thread(
        target=check_inactive_intercoms,
        daemon=True,
        name="Inactive-Checker"
    )
    _check_thread.start()
    print("✓ Inactive intercom checker started (2 min timeout)")

    # Поток для MQTT
    mqtt_thread = threading.Thread(
        target=start_mqtt,
        daemon=True,
        name="MQTT-Client"
    )
    mqtt_thread.start()
    print("✓ MQTT client thread started")


mqtt_client_instance = None

def get_mqtt_client():
    global mqtt_client_instance
    if mqtt_client_instance is None:
        mqtt_client_instance = Client()
        mqtt_client_instance.connect(BROKER, 1883, 60)
        mqtt_client_instance.loop_start()
    return mqtt_client_instance

# Экспортируем для использования в других модулях
mqtt_client = get_mqtt_client()