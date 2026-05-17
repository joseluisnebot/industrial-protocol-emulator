# © mifsut.com — industrial-protocol-emulator
# web/app.py — Panel de control web (FastAPI + WebSocket)

import asyncio
import json
import logging
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from simulator.state import state, PROTOCOLS, reload_protocols
from simulator import config as cfg

log = logging.getLogger("web")

app = FastAPI(title="Industrial Protocol Emulator", version="1.0.0", docs_url=None)

# ── REST API — estado y protocolos ────────────────────────────────────────────

@app.get("/api/state")
async def get_state():
    return JSONResponse(state.snapshot())


@app.get("/api/protocols")
async def get_protocols():
    return JSONResponse(PROTOCOLS)


@app.get("/api/config")
async def get_config():
    """Configuración completa de tags con metadatos de campos editables."""
    return JSONResponse({
        "protocols": PROTOCOLS,
        "editable_fields": cfg.EDITABLE_FIELDS,
        "key_fields": cfg.PROTOCOL_KEY_FIELDS,
    })


# ── REST API — override de señal ──────────────────────────────────────────────

@app.post("/api/override/{protocol}/{tag_id}")
async def set_override(protocol: str, tag_id: str, body: dict):
    if not body:
        await state.set_override(protocol, tag_id, None)
        return {"ok": True, "message": f"{protocol}/{tag_id} → modo automático"}

    override = {
        "min": float(body.get("min", 0)),
        "max": float(body.get("max", 100)),
        "pattern": body.get("pattern", "sine"),
    }
    if override["pattern"] not in ("sine", "ramp", "random", "constant"):
        return JSONResponse({"error": "pattern debe ser: sine, ramp, random, constant"}, status_code=400)
    if override["min"] >= override["max"]:
        return JSONResponse({"error": "min debe ser menor que max"}, status_code=400)

    await state.set_override(protocol, tag_id, override)
    return {"ok": True, "override": override}


# ── REST API — edición de tags ────────────────────────────────────────────────

@app.put("/api/tags/{protocol}")
async def update_protocol_tags(protocol: str, request: Request):
    """
    Guarda la nueva configuración de tags para un protocolo y lo reinicia.
    Body: lista de tags con sus campos actualizados.
    """
    if protocol not in PROTOCOLS:
        return JSONResponse({"error": f"Protocolo desconocido: {protocol}"}, status_code=404)

    try:
        new_tags = await request.json()
    except Exception:
        return JSONResponse({"error": "JSON inválido"}, status_code=400)

    if not isinstance(new_tags, list) or not new_tags:
        return JSONResponse({"error": "Se esperaba una lista de tags"}, status_code=400)

    # Validar que cada tag tenga al menos 'id'
    for tag in new_tags:
        if "id" not in tag:
            return JSONResponse({"error": "Cada tag debe tener 'id'"}, status_code=400)

    # Actualizar PROTOCOLS in-place y guardar
    new_protocols = dict(PROTOCOLS)
    new_protocols[protocol] = new_tags
    reload_protocols(new_protocols)

    # Reinicializar estado del protocolo (limpia tags viejos)
    state.reinit_protocol(protocol)

    # Reiniciar el servidor del protocolo
    start_fn = getattr(app.state, "start_protocol", None)
    if start_fn:
        asyncio.create_task(start_fn(protocol))

    log.info("Tags de %s actualizados (%d tags) — reiniciando", protocol, len(new_tags))
    return {"ok": True, "protocol": protocol, "tags": len(new_tags)}


@app.post("/api/protocol/restart/{protocol}")
async def restart_protocol(protocol: str):
    """Reinicia un servidor de protocolo sin cambiar su config."""
    if protocol not in PROTOCOLS:
        return JSONResponse({"error": f"Protocolo desconocido: {protocol}"}, status_code=404)

    start_fn = getattr(app.state, "start_protocol", None)
    if start_fn:
        asyncio.create_task(start_fn(protocol))
        return {"ok": True, "restarting": protocol}
    return JSONResponse({"error": "Restart no disponible (inicio directo?)"}, status_code=503)


# ── REST API — YAML config ────────────────────────────────────────────────────

@app.get("/api/yaml/{protocol}")
async def get_yaml_config(protocol: str, host: str = "192.168.1.240"):
    tags = PROTOCOLS.get(protocol, [])
    configs = {
        "modbus": lambda: f"""# Pega en devices/modbus/ de tu SCADA
device_id: emulator-modbus
template: generic-modbus
connection:
  host: {host}
  port: 502
  unit_id: 1
poll_interval_ms: 1000
tags:
""" + "".join(
    f"  - id: {t['id']}\n    label: \"{t.get('label', t['id'])}\"\n    address: {t.get('address', 0)}\n    type: {t.get('type','float32')}\n    unit: {t.get('unit','')}\n"
    for t in tags
),
        "opcua": lambda: f"""# Pega en devices/opcua/ de tu SCADA
device_id: emulator-opcua
connection:
  url: opc.tcp://{host}:4840
  namespace: https://mifsut.com/emulator
poll_interval_ms: 2000
tags:
""" + "".join(
    f"  - id: {t['id']}\n    label: \"{t.get('label', t['id'])}\"\n    node: \"{t.get('node_id','')}\"\n    unit: {t.get('unit','')}\n"
    for t in tags
),
        "mqtt": lambda: f"""# Pega en devices/mqtt_ext/ de tu SCADA
device_id: emulator-mqtt
connection:
  host: {host}
  port: 1883
subscriptions:
""" + "".join(
    f"  - id: {t['id']}\n    label: \"{t.get('label', t['id'])}\"\n    topic: {t.get('topic','')}\n    unit: {t.get('unit','')}\n"
    for t in tags
),
        "bacnet": lambda: f"""# Pega en devices/bacnet/ de tu SCADA
device_id: emulator-bacnet
connection:
  host: {host}
  port: 47808
  device_id: 999
objects:
""" + "".join(
    f"  - id: {t['id']}\n    label: \"{t.get('label', t['id'])}\"\n    object_type: analogInput\n    instance: {t.get('instance',0)}\n    unit: {t.get('unit','')}\n"
    for t in tags
),
        "dnp3": lambda: f"""# Pega en devices/dnp3/ de tu SCADA
device_id: emulator-dnp3
connection:
  host: {host}
  port: 20000
tags:
""" + "".join(
    f"  - id: {t['id']}\n    label: \"{t.get('label', t['id'])}\"\n    group: {t.get('group',30)}\n    index: {t.get('index',0)}\n    unit: {t.get('unit','')}\n"
    for t in tags
),
        "ethernetip": lambda: f"""# Pega en devices/ethernet_ip/ de tu SCADA
device_id: emulator-eip
connection:
  host: {host}
  port: 44818
tags:
""" + "".join(
    f"  - id: {t['id']}\n    label: \"{t.get('label', t['id'])}\"\n    tag_name: {t.get('tag_name', t['id'])}\n    type: {t.get('type','REAL')}\n"
    for t in tags
),
        "snmp": lambda: f"""# Pega en devices/snmp/ de tu SCADA
device_id: emulator-snmp
connection:
  host: {host}
  port: 161
  community: public
  version: 2c
oids:
""" + "".join(
    f"  - id: {t['id']}\n    label: \"{t.get('label', t['id'])}\"\n    oid: {t.get('oid','')}\n    unit: {t.get('unit','')}\n"
    for t in tags
),
    }

    if protocol not in configs:
        return JSONResponse({"error": f"Protocolo desconocido: {protocol}"}, status_code=404)

    return JSONResponse({"yaml": configs[protocol](), "protocol": protocol, "host": host})


# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    queue = state.subscribe()
    log.info("WebSocket cliente conectado")
    try:
        await ws.send_json({"type": "snapshot", "data": state.snapshot()})
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=5.0)
                await ws.send_json({"type": "update", "data": msg})
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping", "ts": time.time()})
    except WebSocketDisconnect:
        log.info("WebSocket cliente desconectado")
    except Exception as exc:
        log.error("WebSocket error: %s", exc)
    finally:
        state.unsubscribe(queue)


# ── UI HTML ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))
