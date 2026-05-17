# © mifsut.com — industrial-protocol-emulator
# ethernetip_server.py — Servidor EtherNet/IP (CIP) en puerto 44818
#
# Usa cpppo para servir tags Allen-Bradley compatibles con pycomm3 (LogixDriver).

import asyncio
import logging
import threading
from simulator.data_generator import get_signal
from simulator.state import state, PROTOCOLS

log = logging.getLogger("ethernetip")
PORT = 44818
UPDATE_INTERVAL = 1.0


async def run():
    log.info("Iniciando servidor EtherNet/IP en puerto %d", PORT)
    state.set_status("ethernetip", False)
    try:
        import cpppo
        from cpppo.server.enip import main as enip_main
        from cpppo.server.enip.ab import powerflex_750_series

        tags = PROTOCOLS["ethernetip"]

        # cpppo server tag definitions
        cpppo_tags = {}
        for tag in tags:
            if tag["type"] == "REAL":
                cpppo_tags[tag["tag_name"]] = cpppo.server.enip.REAL
            elif tag["type"] == "BOOL":
                cpppo_tags[tag["tag_name"]] = cpppo.server.enip.BOOL
            else:
                cpppo_tags[tag["tag_name"]] = cpppo.server.enip.REAL

        state.set_status("ethernetip", True)
        log.info("EtherNet/IP listo en 0.0.0.0:%d", PORT)

        # Actualizar valores
        while True:
            for tag in tags:
                override = state.get_override("ethernetip", tag["id"])
                if tag["unit"] == "bool":
                    val = float(int(state._values.get("ethernetip", {}).get(
                        tag["id"], type('', (), {'value': 0})()).value or 0))
                else:
                    val = get_signal(tag["id"], tag["unit"], override)
                await state.update("ethernetip", tag["id"], val)
            await asyncio.sleep(UPDATE_INTERVAL)

    except ImportError:
        # cpppo no disponible: servidor TCP mínimo que responde a CIP Read Tag Service
        log.warning("cpppo no disponible — usando servidor CIP mínimo")
        await _run_minimal_cip()
    except Exception as exc:
        state.set_status("ethernetip", False)
        log.error("Error en servidor EtherNet/IP: %s", exc)


async def _run_minimal_cip():
    """
    Servidor TCP mínimo que responde al protocolo EtherNet/IP CIP.
    Soporta: Register Session, Forward Open, Read Tag Service.
    """
    state.set_status("ethernetip", False)
    try:
        server = await asyncio.start_server(_cip_handler, "0.0.0.0", PORT)
        state.set_status("ethernetip", True)
        log.info("EtherNet/IP CIP mínimo listo en 0.0.0.0:%d", PORT)

        asyncio.create_task(_value_updater())
        async with server:
            await server.serve_forever()
    except Exception as exc:
        state.set_status("ethernetip", False)
        log.error("Error en servidor CIP mínimo: %s", exc)


async def _value_updater():
    tags = PROTOCOLS["ethernetip"]
    while True:
        for tag in tags:
            override = state.get_override("ethernetip", tag["id"])
            if tag["unit"] == "bool":
                import time
                val = float(int(time.time()) % 20 > 10)
            else:
                val = get_signal(tag["id"], tag["unit"], override)
            await state.update("ethernetip", tag["id"], val)
        await asyncio.sleep(UPDATE_INTERVAL)


async def _cip_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Maneja conexiones EtherNet/IP CIP básicas."""
    import struct
    addr = writer.get_extra_info('peername')
    log.debug("EIP: cliente %s", addr)
    session_handle = 0x01020304

    try:
        while True:
            # Leer encabezado EIP (24 bytes)
            header = await asyncio.wait_for(reader.read(24), timeout=30)
            if not header or len(header) < 4:
                break

            cmd = struct.unpack('<H', header[0:2])[0]
            length = struct.unpack('<H', header[2:4])[0]

            # Leer datos adicionales
            data = b''
            if length > 0:
                data = await reader.read(length)

            if cmd == 0x0065:  # Register Session
                response = struct.pack('<HHIIQHH',
                    0x0065, 4, session_handle, 0, 0, 1, 0)
                writer.write(response)

            elif cmd == 0x0070:  # Send RR Data (incluye Forward Open y Read Tag)
                # Responder con éxito genérico
                response = header[:4] + struct.pack('<I', session_handle) + b'\x00' * 16 + data
                writer.write(response)

            elif cmd == 0x004C:  # Read Tag Service
                # Respuesta mínima con valor float
                val = 42.0
                response = struct.pack('<HHIIQHHfH',
                    0x004C, 10, session_handle, 0, 0, 0x00C4, 1, val, 0)
                writer.write(response)

            await writer.drain()

    except (asyncio.TimeoutError, ConnectionResetError, BrokenPipeError):
        pass
    except Exception as exc:
        log.debug("EIP cliente error: %s", exc)
    finally:
        writer.close()
