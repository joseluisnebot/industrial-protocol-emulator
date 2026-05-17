# © mifsut.com — industrial-protocol-emulator
# main.py — Orquestador asyncio con soporte de restart por protocolo

import asyncio
import importlib
import logging
import signal
import uvicorn

from simulator.web.app import app as web_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)-12s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")

WEB_HOST = "0.0.0.0"
WEB_PORT = 8080

PROTOCOL_MODULES = {
    "modbus":     "simulator.protocols.modbus_server",
    "opcua":      "simulator.protocols.opcua_server",
    "mqtt":       "simulator.protocols.mqtt_publisher",
    "bacnet":     "simulator.protocols.bacnet_server",
    "dnp3":       "simulator.protocols.dnp3_server",
    "ethernetip": "simulator.protocols.ethernetip_server",
    "snmp":       "simulator.protocols.snmp_agent",
}

# Mapa global de tareas activas — accesible desde la web API
protocol_tasks: dict[str, asyncio.Task] = {}


async def _run_protocol(name: str, module_path: str):
    try:
        mod = importlib.import_module(module_path)
        # Forzar recarga del módulo para que lea la nueva config
        importlib.reload(mod)
        log.info("Iniciando protocolo: %s", name)
        await mod.run()
    except ImportError as exc:
        log.warning("Protocolo %s: librería no disponible — %s", name, exc)
    except asyncio.CancelledError:
        log.info("Protocolo %s detenido.", name)
    except Exception as exc:
        log.error("Protocolo %s falló: %s", name, exc, exc_info=True)


async def start_protocol(name: str):
    """Lanza (o relanza) un protocolo como tarea asyncio."""
    if name in protocol_tasks and not protocol_tasks[name].done():
        protocol_tasks[name].cancel()
        try:
            await asyncio.wait_for(asyncio.shield(protocol_tasks[name]), timeout=3)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    module_path = PROTOCOL_MODULES.get(name)
    if not module_path:
        log.error("Protocolo desconocido: %s", name)
        return

    task = asyncio.create_task(_run_protocol(name, module_path), name=f"proto-{name}")
    protocol_tasks[name] = task
    return task


async def run_web():
    config = uvicorn.Config(
        web_app,
        host=WEB_HOST,
        port=WEB_PORT,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    log.info("Panel web en http://%s:%d", WEB_HOST, WEB_PORT)
    await server.serve()


async def main():
    log.info("=" * 60)
    log.info("  Industrial Protocol Emulator — mifsut.com")
    log.info("=" * 60)

    # Exponer start_protocol a la web app
    web_app.state.start_protocol = start_protocol

    # Arrancar todos los protocolos
    for name in PROTOCOL_MODULES:
        await start_protocol(name)

    web_task = asyncio.create_task(run_web(), name="web")

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _shutdown():
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown)

    await stop_event.wait()
    log.info("Deteniendo emulador...")

    web_task.cancel()
    for task in protocol_tasks.values():
        task.cancel()
    await asyncio.gather(*protocol_tasks.values(), web_task, return_exceptions=True)
    log.info("Emulador detenido.")


if __name__ == "__main__":
    asyncio.run(main())
