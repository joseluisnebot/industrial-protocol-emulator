# © mifsut.com — industrial-protocol-emulator
# main.py — Orquestador asyncio: lanza todos los servidores de protocolo + UI web

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

PROTOCOL_MODULES = [
    ("modbus",      "simulator.protocols.modbus_server"),
    ("opcua",       "simulator.protocols.opcua_server"),
    ("mqtt",        "simulator.protocols.mqtt_publisher"),
    ("bacnet",      "simulator.protocols.bacnet_server"),
    ("dnp3",        "simulator.protocols.dnp3_server"),
    ("ethernetip",  "simulator.protocols.ethernetip_server"),
    ("snmp",        "simulator.protocols.snmp_agent"),
]


async def run_protocol(name: str, module_path: str):
    """Importa y ejecuta un servidor de protocolo, aislando excepciones."""
    try:
        mod = importlib.import_module(module_path)
        log.info("Iniciando protocolo: %s", name)
        await mod.run()
    except ImportError as exc:
        log.warning("Protocolo %s: librería no disponible — %s", name, exc)
    except Exception as exc:
        log.error("Protocolo %s falló: %s", name, exc, exc_info=True)


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

    tasks = [asyncio.create_task(run_protocol(name, mod)) for name, mod in PROTOCOL_MODULES]
    tasks.append(asyncio.create_task(run_web()))

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: [t.cancel() for t in tasks])

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        log.info("Emulador detenido.")


if __name__ == "__main__":
    asyncio.run(main())
