# © mifsut.com — industrial-protocol-emulator
# web/app.py — Panel de control web (FastAPI + WebSocket)

import asyncio
import json
import logging
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from simulator.state import state, PROTOCOLS

log = logging.getLogger("web")

app = FastAPI(title="Industrial Protocol Emulator", version="1.0.0", docs_url=None)

# ── REST API ──────────────────────────────────────────────────────────────────

@app.get("/api/state")
async def get_state():
    """Estado completo de todos los protocolos y tags."""
    return JSONResponse(state.snapshot())


@app.get("/api/protocols")
async def get_protocols():
    """Lista de protocolos y definición de tags."""
    return JSONResponse(PROTOCOLS)


@app.post("/api/override/{protocol}/{tag_id}")
async def set_override(protocol: str, tag_id: str, body: dict):
    """
    Sobreescribe los parámetros de generación de señal para un tag.
    Body: {"min": 0, "max": 100, "pattern": "sine|ramp|random|constant"}
    Para resetear al modo automático, enviar body vacío {}.
    """
    if not body:
        await state.set_override(protocol, tag_id, None)
        return {"ok": True, "message": f"{protocol}/{tag_id} → modo automático"}

    override = {
        "min": float(body.get("min", 0)),
        "max": float(body.get("max", 100)),
        "pattern": body.get("pattern", "sine"),
    }
    # Validar pattern
    if override["pattern"] not in ("sine", "ramp", "random", "constant"):
        return JSONResponse({"error": "pattern debe ser: sine, ramp, random, constant"}, status_code=400)
    if override["min"] >= override["max"]:
        return JSONResponse({"error": "min debe ser menor que max"}, status_code=400)

    await state.set_override(protocol, tag_id, override)
    return {"ok": True, "override": override}


@app.get("/api/yaml/{protocol}")
async def get_yaml_config(protocol: str, host: str = "192.168.1.240"):
    """
    Genera el YAML de dispositivo listo para pegar en el SCADA.
    host: IP del servidor donde corre el emulador (por defecto 192.168.1.240)
    """
    configs = {
        "modbus": f"""# Pega este archivo en devices/modbus/ de tu instalación SCADA
# Nombre sugerido: emulator-modbus.yaml
device_id: emulator-modbus
template: generic-modbus
connection:
  host: {host}
  port: 502
  unit_id: 1
poll_interval_ms: 1000
""",
        "opcua": f"""# Pega este archivo en devices/opcua/ de tu instalación SCADA
device_id: emulator-opcua
template: generic-opcua
connection:
  url: opc.tcp://{host}:4840
poll_interval_ms: 2000
""",
        "mqtt": f"""# Pega este archivo en devices/mqtt_ext/ de tu instalación SCADA
device_id: emulator-mqtt
template: generic-mqtt-device
connection:
  host: {host}
  port: 1883
poll_interval_ms: 1000
""",
        "bacnet": f"""# Pega este archivo en devices/bacnet/ de tu instalación SCADA
device_id: emulator-bacnet
template: generic-bacnet
connection:
  host: {host}
poll_interval_ms: 2000
""",
        "dnp3": f"""# Pega este archivo en devices/dnp3/ de tu instalación SCADA
device_id: emulator-dnp3
template: generic-dnp3
connection:
  host: {host}
  port: 20000
poll_interval_ms: 2000
""",
        "ethernetip": f"""# Pega este archivo en devices/ethernet_ip/ de tu instalación SCADA
device_id: emulator-eip
template: allen-bradley-compactlogix
connection:
  host: {host}
poll_interval_ms: 1000
""",
        "snmp": f"""# Pega este archivo en devices/snmp/ de tu instalación SCADA
device_id: emulator-snmp
template: generic-snmp
connection:
  host: {host}
poll_interval_ms: 5000
""",
    }
    if protocol not in configs:
        return JSONResponse({"error": f"Protocolo desconocido: {protocol}"}, status_code=404)
    return JSONResponse({"yaml": configs[protocol], "protocol": protocol, "host": host})


# ── WebSocket (tiempo real) ───────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    queue = state.subscribe()
    log.info("WebSocket cliente conectado")
    try:
        # Enviar estado inicial completo
        await ws.send_json({"type": "snapshot", "data": state.snapshot()})
        # Stream de actualizaciones
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=5.0)
                await ws.send_json({"type": "update", "data": msg})
            except asyncio.TimeoutError:
                # Heartbeat
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
