# © mifsut.com — industrial-protocol-emulator
# config.py — Configuración persistente de tags (JSON) con defaults integrados

import json
import logging
from pathlib import Path

log = logging.getLogger("config")

CONFIG_PATH = Path(__file__).parent.parent / "data" / "custom_tags.json"

# ── Configuración por defecto ─────────────────────────────────────────────────
# Cada tag tiene campos comunes + campos específicos del protocolo.
# Campos comunes: id, label, unit, min, max
# Campos específicos por protocolo se definen abajo.

DEFAULTS: dict[str, list[dict]] = {
    "modbus": [
        {"id": "frecuencia_salida", "label": "Output Frequency", "address": 0,  "unit": "Hz",  "type": "float32", "min": 0,   "max": 60},
        {"id": "corriente_motor",   "label": "Motor Current",   "address": 2,  "unit": "A",   "type": "float32", "min": 0,   "max": 100},
        {"id": "tension_dc",        "label": "DC Voltage",        "address": 4,  "unit": "V",   "type": "float32", "min": 200, "max": 480},
        {"id": "temperatura_igbt",  "label": "IGBT Temperature",  "address": 6,  "unit": "°C",  "type": "float32", "min": 20,  "max": 90},
        {"id": "potencia_activa",   "label": "Active Power",   "address": 8,  "unit": "kW",  "type": "float32", "min": 0,   "max": 200},
    ],
    "opcua": [
        {"id": "Motor_Speed",   "label": "Motor Speed",   "node_id": "ns=2;s=Motor/Speed",   "unit": "rpm", "min": 0,   "max": 3000},
        {"id": "Motor_Current", "label": "Motor Current",   "node_id": "ns=2;s=Motor/Current", "unit": "A",   "min": 0,   "max": 100},
        {"id": "Temp_Ambient",  "label": "Ambient Temperature", "node_id": "ns=2;s=Temp/Ambient","unit": "°C", "min": -20, "max": 80},
    ],
    "mqtt": [
        {"id": "temperatura", "label": "Temperature",  "topic": "plant/sensor1/temperature", "unit": "°C",  "min": -20,  "max": 80},
        {"id": "humedad",     "label": "Humidity",       "topic": "plant/sensor1/humidity",     "unit": "%",   "min": 0,    "max": 100},
        {"id": "energia",     "label": "Energy",       "topic": "plant/meter/energy",    "unit": "kWh", "min": 0,    "max": 9999},
    ],
    "bacnet": [
        {"id": "temperatura", "label": "Temperature", "instance": 1, "unit": "°C",  "min": -20, "max": 80},
        {"id": "presion",     "label": "Pressure",     "instance": 2, "unit": "bar", "min": 0,   "max": 10},
        {"id": "caudal",      "label": "Flow",      "instance": 3, "unit": "m3/h","min": 0,   "max": 500},
    ],
    "dnp3": [
        {"id": "voltaje",            "label": "Voltage",            "group": 30, "variation": 5, "index": 0, "unit": "V",    "min": 0,  "max": 480},
        {"id": "corriente",          "label": "Current",          "group": 30, "variation": 5, "index": 1, "unit": "A",    "min": 0,  "max": 100},
        {"id": "potencia",           "label": "Power",           "group": 30, "variation": 5, "index": 2, "unit": "kW",   "min": 0,  "max": 200},
        {"id": "estado_interruptor", "label": "Breaker State", "group": 1,  "variation": 2, "index": 0, "unit": "bool", "min": 0,  "max": 1},
    ],
    "ethernetip": [
        {"id": "Motor_Speed",      "label": "Motor Speed",   "tag_name": "Motor_Speed",      "unit": "rpm",  "type": "REAL", "min": 0,  "max": 3000},
        {"id": "Motor_Current",    "label": "Motor Current",   "tag_name": "Motor_Current",    "unit": "A",    "type": "REAL", "min": 0,  "max": 100},
        {"id": "Conveyor_Running", "label": "Conveyor Running",   "tag_name": "Conveyor_Running", "unit": "bool", "type": "BOOL", "min": 0,  "max": 1},
    ],
    "snmp": [
        {"id": "cpu_load",    "label": "CPU Load",    "oid": "1.3.6.1.4.1.9999.1.1.0", "unit": "%",  "snmp_type": "gauge32",         "min": 0,   "max": 100},
        {"id": "temperatura", "label": "Temperature", "oid": "1.3.6.1.4.1.9999.1.2.0", "unit": "°C", "snmp_type": "integer32_x100",  "min": -20, "max": 85},
        {"id": "uptime",      "label": "Uptime",      "oid": "1.3.6.1.4.1.9999.1.3.0", "unit": "s",  "snmp_type": "counter32",       "min": 0,   "max": 999999},
    ],
}

# Campos que son "identificadores de protocolo" — cambiarlos requiere restart
PROTOCOL_KEY_FIELDS = {
    "modbus":     ["address", "type"],
    "opcua":      ["node_id"],
    "mqtt":       ["topic"],
    "bacnet":     ["instance"],
    "dnp3":       ["group", "variation", "index"],
    "ethernetip": ["tag_name", "type"],
    "snmp":       ["oid"],
}

# Campos editables por protocolo (para la UI)
EDITABLE_FIELDS = {
    "modbus":     [
        {"key": "label",   "label": "Nombre",    "type": "text"},
        {"key": "unit",    "label": "Unidad",    "type": "text"},
        {"key": "address", "label": "Registro (Holding, offset de 16-bit)",  "type": "number"},
        {"key": "min",     "label": "Signal min", "type": "number"},
        {"key": "max",     "label": "Signal max", "type": "number"},
    ],
    "opcua": [
        {"key": "label",   "label": "Nombre",   "type": "text"},
        {"key": "unit",    "label": "Unidad",   "type": "text"},
        {"key": "node_id", "label": "Node ID",  "type": "text"},
        {"key": "min",     "label": "Signal min","type": "number"},
        {"key": "max",     "label": "Signal max","type": "number"},
    ],
    "mqtt": [
        {"key": "label", "label": "Nombre",     "type": "text"},
        {"key": "unit",  "label": "Unidad",     "type": "text"},
        {"key": "topic", "label": "Topic MQTT", "type": "text"},
        {"key": "min",   "label": "Signal min",  "type": "number"},
        {"key": "max",   "label": "Signal max",  "type": "number"},
    ],
    "bacnet": [
        {"key": "label",    "label": "Nombre",   "type": "text"},
        {"key": "unit",     "label": "Unidad",   "type": "text"},
        {"key": "instance", "label": "Instance", "type": "number"},
        {"key": "min",      "label": "Signal min","type": "number"},
        {"key": "max",      "label": "Signal max","type": "number"},
    ],
    "dnp3": [
        {"key": "label", "label": "Nombre",  "type": "text"},
        {"key": "unit",  "label": "Unidad",  "type": "text"},
        {"key": "index", "label": "Índice",  "type": "number"},
        {"key": "min",   "label": "Signal min","type": "number"},
        {"key": "max",   "label": "Signal max","type": "number"},
    ],
    "ethernetip": [
        {"key": "label",    "label": "Nombre",    "type": "text"},
        {"key": "unit",     "label": "Unidad",    "type": "text"},
        {"key": "tag_name", "label": "Tag Name",  "type": "text"},
        {"key": "min",      "label": "Signal min", "type": "number"},
        {"key": "max",      "label": "Signal max", "type": "number"},
    ],
    "snmp": [
        {"key": "label",     "label": "Nombre",    "type": "text"},
        {"key": "unit",      "label": "Unidad",    "type": "text"},
        {"key": "oid",       "label": "OID",       "type": "text"},
        {"key": "snmp_type", "label": "Tipo SNMP (gauge32 / integer32_x100 / integer32 / counter32)", "type": "text"},
        {"key": "min",       "label": "Signal min", "type": "number"},
        {"key": "max",       "label": "Signal max", "type": "number"},
    ],
}


def load() -> dict:
    """Carga config desde JSON; si no existe devuelve los defaults."""
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            # Merge: si falta algún protocolo usamos el default
            for proto, tags in DEFAULTS.items():
                if proto not in data:
                    data[proto] = tags
            log.info("Config loaded from %s", CONFIG_PATH)
            return data
        except Exception as exc:
            log.warning("Error reading config (%s) — using defaults", exc)
    return {k: [t.copy() for t in v] for k, v in DEFAULTS.items()}


def save(protocols: dict):
    """Guarda la config completa a JSON."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(protocols, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info("Config saved to %s", CONFIG_PATH)
