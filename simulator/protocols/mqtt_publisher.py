# © mifsut.com — industrial-protocol-emulator
# mqtt_publisher.py — Broker Mosquitto + Publisher MQTT en puerto 1883

import asyncio
import json
import logging
import time
import paho.mqtt.client as mqtt
from simulator.data_generator import get_signal
from simulator.state import state, PROTOCOLS

log = logging.getLogger("mqtt")
BROKER_HOST = "localhost"
BROKER_PORT = 1883
UPDATE_INTERVAL = 1.0


async def run():
    log.info("Iniciando publisher MQTT → %s:%d", BROKER_HOST, BROKER_PORT)
    state.set_status("mqtt", False)

    loop = asyncio.get_event_loop()

    client = mqtt.Client(client_id="ipe-publisher", protocol=mqtt.MQTTv5)

    connected = asyncio.Event()

    def on_connect(c, userdata, flags, rc, props=None):
        if rc == 0:
            log.info("MQTT conectado al broker %s:%d", BROKER_HOST, BROKER_PORT)
            state.set_status("mqtt", True)
            loop.call_soon_threadsafe(connected.set)
        else:
            log.error("MQTT error de conexión: rc=%d", rc)

    def on_disconnect(c, userdata, rc, props=None):
        log.warning("MQTT desconectado rc=%d", rc)
        state.set_status("mqtt", False)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    try:
        # Intentar conectar con reintentos
        for attempt in range(10):
            try:
                client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
                break
            except Exception:
                log.warning("MQTT broker no disponible, reintento %d/10...", attempt + 1)
                await asyncio.sleep(3)

        client.loop_start()
        await asyncio.wait_for(connected.wait(), timeout=30)

        tags = PROTOCOLS["mqtt"]
        while True:
            for tag in tags:
                override = state.get_override("mqtt", tag["id"])
                val = get_signal(tag["id"], tag["unit"], override)
                await state.update("mqtt", tag["id"], val)
                payload = json.dumps({"value": val, "unit": tag["unit"], "ts": int(time.time() * 1000)})
                client.publish(tag["topic"], payload, qos=0, retain=False)
                log.debug("MQTT publish %s → %s = %.3f %s", tag["topic"], tag["id"], val, tag["unit"])
            await asyncio.sleep(UPDATE_INTERVAL)

    except asyncio.TimeoutError:
        log.error("MQTT: timeout esperando conexión al broker")
        state.set_status("mqtt", False)
    except Exception as exc:
        state.set_status("mqtt", False)
        log.error("Error en publisher MQTT: %s", exc)
    finally:
        client.loop_stop()
        client.disconnect()
