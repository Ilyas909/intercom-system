import time
import json
import random
import threading
from datetime import datetime
from typing import Dict, Optional
import os
from paho.mqtt import client as mqtt

class IntercomEmulator:
    """Эмулятор одного домофона"""

    def __init__(self, mac: str, broker: str = "localhost", port: int = 1883):
        self.mac = mac
        self.broker = broker
        self.port = port
        self.door_status = "closed"
        self.last_heartbeat = None

        # Настройки вероятностей событий (0.0 - 1.0)
        self.call_probability = 0.2  # 5% шанс звонка при каждом хардбит
        self.key_probability = 0.15  # 3% шанс использования ключа

        # Возможные квартиры для этого домофона
        self.apartments = list(range(1, 21))  # Квартиры 1-20

        # Инициализация MQTT клиента
        try:
            # Для paho-mqtt >= 2.0
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"intercom_{mac}")
        except AttributeError:
            # Для старых версий (совместимость)
            self.client = mqtt.Client(client_id=f"intercom_{mac}")
        self.client.on_message = self.on_message
        self.client.on_connect = self.on_connect

        print(f"Intercom {self.mac} initialized")

    def on_connect(self, client, userdata, flags, rc, properties=None):
        """Обработчик подключения к MQTT"""
        if rc == 0:
            print(f"✅ {self.mac}: Connected to MQTT broker")
            self.client.subscribe(f"intercom/{self.mac}/cmd")
            print(f"{self.mac}: Subscribed to commands")
        else:
            print(f"❌ {self.mac}: Failed to connect (code {rc})")

    def on_message(self, client, userdata, msg):
        """Обработчик входящих команд"""
        try:
            data = json.loads(msg.payload.decode())
            if data.get("action") == "open":
                print(f"{self.mac}: opening the door from the server")
                # Меняем статус двери
                self.door_status = "open"
                # Отправляем событие открытия
                self.publish_event(
                    "door_opened",
                    {
                        "source": "remote",
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )

                # Автоматически закрываем через 5 секунд
                threading.Timer(5.0, self.auto_close_door).start()

        except Exception as e:
            print(f"❌ {self.mac}: Error handling message: {e}")

    def auto_close_door(self):
        """Автоматически закрывает дверь через 5 секунд"""
        self.door_status = "closed"

    def publish_event(self, event_type: str, payload: Dict):
        """Отправляет событие в MQTT"""
        topic = f"intercom/{self.mac}/{event_type}"
        self.client.publish(topic, json.dumps(payload))

    def heartbeat(self):
        """Отправляет heartbeat с информацией о статусе"""
        payload = {
            "door_status": self.door_status,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.publish_event("heartbeat", payload)
        self.last_heartbeat = datetime.utcnow()

    def simulate_call(self):
        """Симулирует звонок в случайную квартиру"""
        apartment = random.choice(self.apartments)
        payload = {
            "apartment": apartment,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.publish_event("call", payload)


    def simulate_key(self):
        """Симулирует использование ключа"""
        apartment = random.choice(self.apartments)
        payload = {
            "apartment": apartment,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.publish_event("key", payload)


    def start(self):
        """Запускает эмулятор"""
        self.client.connect(self.broker, self.port, 60)
        self.client.loop_start()

        # Основной цикл
        try:
            while True:
                # Отправляем heartbeat каждые 30 секунд
                self.heartbeat()

                # Случайные события
                if random.random() < self.call_probability:
                    self.simulate_call()

                if random.random() < self.key_probability:
                    self.simulate_key()

                time.sleep(30)

        except KeyboardInterrupt:
            print(f"\n{self.mac}: Shutting down...")
            self.client.loop_stop()
            self.client.disconnect()


def run_single_intercom():
    """Запускает один домофон (для тестирования)"""
    intercom = IntercomEmulator("AA:BB:CC:01")
    intercom.start()


def run_multiple_intercoms():
    """Запускает несколько домофонов в отдельных потоках"""

    # Конфигурация домофонов
    intercom_configs = [
        {"mac": "AA:BB:CC:01", "apartments": list(range(1, 11))},
        {"mac": "AA:BB:CC:02", "apartments": list(range(11, 21))},
        {"mac": "AA:BB:CC:03", "apartments": list(range(21, 31))},
        {"mac": "AA:BB:CC:04", "apartments": list(range(31, 41))},
    ]

    broker = os.getenv("MQTT_BROKER", "mosquitto")

    intercoms = []

    for config in intercom_configs:
        intercom = IntercomEmulator(config["mac"], broker=broker)
        intercom.apartments = config["apartments"]
        intercoms.append(intercom)

        # Запускаем в отдельном потоке
        thread = threading.Thread(
            target=intercom.start,
            daemon=True,
            name=f"Intercom-{config['mac']}"
        )
        thread.start()
        print(f"Started thread for {config['mac']}")

    print(f"\nStarted {len(intercoms)} intercom emulators")
    print("Press Ctrl+C to stop\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down all intercoms...")
        for intercom in intercoms:
            intercom.client.loop_stop()
            intercom.client.disconnect()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "single":
        print("Running single intercom mode...\n")
        run_single_intercom()
    else:
        print("Running multiple intercoms mode...\n")
        run_multiple_intercoms()