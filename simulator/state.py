# © mifsut.com — industrial-protocol-emulator
# state.py — Estado compartido entre todos los servidores de protocolo y la web UI

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

# ── Definición de tags por protocolo ──────────────────────────────────────────

PROTOCOLS: dict[str, list[dict]] = {
    "modbus": [
        {"id": "frecuencia_salida",  "address": 40001, "unit": "Hz",  "type": "float32", "scale": 0.01},
        {"id": "corriente_motor",    "address": 40003, "unit": "A",   "type": "float32", "scale": 0.1},
        {"id": "tension_dc",         "address": 40005, "unit": "V",   "type": "float32", "scale": 0.1},
        {"id": "temperatura_igbt",   "address": 40015, "unit": "°C",  "type": "float32", "scale": 0.1},
        {"id": "potencia_activa",    "address": 40007, "unit": "kW",  "type": "float32", "scale": 0.1},
    ],
    "opcua": [
        {"id": "Motor_Speed",    "node_id": "ns=2;s=Motor/Speed",    "unit": "rpm"},
        {"id": "Motor_Current",  "node_id": "ns=2;s=Motor/Current",  "unit": "A"},
        {"id": "Temp_Ambient",   "node_id": "ns=2;s=Temp/Ambient",   "unit": "°C"},
    ],
    "mqtt": [
        {"id": "temperatura", "topic": "planta/sensor1/temperatura", "unit": "°C"},
        {"id": "humedad",     "topic": "planta/sensor1/humedad",     "unit": "%"},
        {"id": "energia",     "topic": "planta/contador/energia",    "unit": "kWh"},
    ],
    "bacnet": [
        {"id": "temperatura", "object_type": "analogInput",  "instance": 1, "unit": "°C"},
        {"id": "presion",     "object_type": "analogInput",  "instance": 2, "unit": "bar"},
        {"id": "caudal",      "object_type": "analogInput",  "instance": 3, "unit": "m3/h"},
    ],
    "dnp3": [
        {"id": "voltaje",            "group": 30, "variation": 5, "index": 0, "unit": "V"},
        {"id": "corriente",          "group": 30, "variation": 5, "index": 1, "unit": "A"},
        {"id": "potencia",           "group": 30, "variation": 5, "index": 2, "unit": "kW"},
        {"id": "estado_interruptor", "group": 1,  "variation": 2, "index": 0, "unit": "bool"},
    ],
    "ethernetip": [
        {"id": "Motor_Speed",       "tag_name": "Motor_Speed",       "unit": "rpm",  "type": "REAL"},
        {"id": "Motor_Current",     "tag_name": "Motor_Current",     "unit": "A",    "type": "REAL"},
        {"id": "Conveyor_Running",  "tag_name": "Conveyor_Running",  "unit": "bool", "type": "BOOL"},
    ],
    "snmp": [
        {"id": "cpu_load",    "oid": "1.3.6.1.4.1.9999.1.1.0", "unit": "%"},
        {"id": "temperatura", "oid": "1.3.6.1.4.1.9999.1.2.0", "unit": "°C"},
        {"id": "uptime",      "oid": "1.3.6.1.4.1.9999.1.3.0", "unit": "s"},
    ],
}

# ── Estado en tiempo real ──────────────────────────────────────────────────────

@dataclass
class TagState:
    value: float = 0.0
    unit: str = ""
    ts: float = field(default_factory=time.time)
    override: dict | None = None   # {min, max, pattern} o None para auto


class SimulatorState:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._values: dict[str, dict[str, TagState]] = {}
        self._server_status: dict[str, bool] = {}
        self._subscribers: list[asyncio.Queue] = []

        # Inicializar estado vacío
        for proto, tags in PROTOCOLS.items():
            self._values[proto] = {}
            for tag in tags:
                self._values[proto][tag["id"]] = TagState(unit=tag.get("unit", ""))
            self._server_status[proto] = False

    async def update(self, protocol: str, tag_id: str, value: float):
        async with self._lock:
            if protocol in self._values and tag_id in self._values[protocol]:
                self._values[protocol][tag_id].value = value
                self._values[protocol][tag_id].ts = time.time()
        await self._notify(protocol, tag_id, value)

    async def set_override(self, protocol: str, tag_id: str, override: dict | None):
        async with self._lock:
            if protocol in self._values and tag_id in self._values[protocol]:
                self._values[protocol][tag_id].override = override

    def get_override(self, protocol: str, tag_id: str) -> dict | None:
        return self._values.get(protocol, {}).get(tag_id, TagState()).override

    def snapshot(self) -> dict:
        result = {}
        for proto, tags in self._values.items():
            result[proto] = {
                "online": self._server_status.get(proto, False),
                "tags": {
                    tid: {"value": ts.value, "unit": ts.unit, "ts": ts.ts, "override": ts.override}
                    for tid, ts in tags.items()
                },
            }
        return result

    def set_status(self, protocol: str, online: bool):
        self._server_status[protocol] = online

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        self._subscribers.discard(q) if hasattr(self._subscribers, 'discard') else None
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    async def _notify(self, protocol: str, tag_id: str, value: float):
        msg = {"protocol": protocol, "tag_id": tag_id, "value": value, "ts": time.time()}
        for q in list(self._subscribers):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass


# Singleton global
state = SimulatorState()
