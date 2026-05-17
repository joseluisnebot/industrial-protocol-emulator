# © mifsut.com — industrial-protocol-emulator
# main.py — Orquestador asyncio: lanza todos los servidores de protocolo + UI web

import asyncio
import logging
import signal
import sys
import uvicorn

from simulator.protocols import (
    modbus_server,
    opcua_server,
    mqtt_publisher,
    bacnet_server,
    dnp3_server,
    ethernetip_server,
    snmp_agent,
)
from simulator.web.app import app as web_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)-12s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")

WEB_HOST = "0.0.0.0"
WEB_PORT = 8080


async def run_protocol(name: str, coro):
    """Ejecuta un servidor de protocolo, capturando excepciones sin derribar el proceso."""
    try:
        log.info("Iniciando protocolo: %s", name)
        await coro()
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

    tasks = [
        asyncio.create_task(run_protocol("modbus",      modbus_server.run)),
        asyncio.create_task(run_protocol("opcua",       opcua_server.run)),
        asyncio.create_task(run_protocol("mqtt",        mqtt_publisher.run)),
        asyncio.create_task(run_protocol("bacnet",      bacnet_server.run)),
        asyncio.create_task(run_protocol("dnp3",        dnp3_server.run)),
        asyncio.create_task(run_protocol("ethernetip",  ethernetip_server.run)),
        asyncio.create_task(run_protocol("snmp",        snmp_agent.run)),
        asyncio.create_task(run_web()),
    ]

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: [t.cancel() for t in tasks])

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        log.info("Emulador detenido.")


if __name__ == "__main__":
    asyncio.run(main())
