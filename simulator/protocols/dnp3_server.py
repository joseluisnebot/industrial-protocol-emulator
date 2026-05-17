# © mifsut.com — industrial-protocol-emulator
# dnp3_server.py — Servidor DNP3 stub TCP en puerto 20000
#
# Implementa un subconjunto mínimo del protocolo DNP3 suficiente para responder
# a Integrity Polls del driver SCADA (lectura de Analog Inputs).
# Soporta: DATA_LINK layer + APPLICATION layer básico (Class 0 Poll / Integrity Poll)

import asyncio
import logging
import struct
import time
from simulator.data_generator import get_signal
from simulator.state import state, PROTOCOLS

log = logging.getLogger("dnp3")
PORT = 20000
UPDATE_INTERVAL = 1.0

# Constantes DNP3
DNP3_START_BYTES = b'\x05\x64'
APP_CTRL_FIR_FIN = 0xC0  # First + Final fragment
FC_RESPONSE = 0x81        # Application layer: Response
FC_UNSOLICITED = 0x82
GRP30_VAR5 = (30, 5)      # Analog Input — float32
GRP1_VAR2  = (1, 2)       # Binary Input — with flags


def _crc16(data: bytes) -> int:
    crc = 0x0000
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA6BC
            else:
                crc >>= 1
    return (~crc) & 0xFFFF


def _build_analog_input_response(values: list[float], seq: int) -> bytes:
    """Construye una respuesta DNP3 con Analog Inputs (Group 30 Var 5)."""
    # Application layer objects: G30V5 (float32) con flags = 0x00
    objects = b''
    for i, val in enumerate(values):
        flags = 0x01  # ONLINE
        objects += struct.pack('<Bf', flags, val)

    # Object header: G30 V5, 0x01 (Count of Objects), start_idx, stop_idx
    obj_header = struct.pack('BBBBBi',
        30, 5,  # Group, Variation
        0x28,   # Qualifier: 8-bit count
        len(values),  # count
        0x00, 0x00    # padding (simplificado)
    )
    # Simplificado: usar qualifier 0x17 (count + 0-based index)
    obj_header = bytes([30, 5, 0x28, len(values)])
    app_payload = bytes([APP_CTRL_FIR_FIN | (seq & 0x0F), FC_RESPONSE, 0x00, 0x00]) + obj_header + objects

    # Data Link layer
    length = 5 + len(app_payload)
    dl_header = DNP3_START_BYTES + bytes([length, 0x44, 0x01, 0x00, 0x04, 0x00])
    dl_crc = _crc16(dl_header[2:])
    dl_header += struct.pack('<H', dl_crc)

    # Fragmentar app_payload en bloques de 16 bytes con CRC
    payload_blocks = b''
    for i in range(0, len(app_payload), 16):
        block = app_payload[i:i+16]
        crc = _crc16(block)
        payload_blocks += block + struct.pack('<H', crc)

    return dl_header + payload_blocks


async def _handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    addr = writer.get_extra_info('peername')
    log.info("DNP3: cliente conectado desde %s", addr)
    seq = 0
    try:
        while True:
            # Leer cabecera data link (10 bytes)
            try:
                header = await asyncio.wait_for(reader.read(10), timeout=30)
            except asyncio.TimeoutError:
                break
            if not header or len(header) < 2:
                break
            if header[:2] != DNP3_START_BYTES:
                continue

            # Leer resto del frame
            if len(header) >= 3:
                frame_len = header[2]
                rest = await reader.read(frame_len + 2)  # +2 por CRC data link

            # Construir respuesta con los valores actuales
            tags = PROTOCOLS["dnp3"]
            analog_vals = []
            for tag in tags:
                if tag["group"] == 30:
                    val = state._values.get("dnp3", {}).get(tag["id"])
                    analog_vals.append(val.value if val else 0.0)

            response = _build_analog_input_response(analog_vals, seq)
            writer.write(response)
            await writer.drain()
            seq = (seq + 1) & 0x0F
            log.debug("DNP3: respondido integrity poll con %d AI values", len(analog_vals))

    except (ConnectionResetError, BrokenPipeError):
        pass
    except Exception as exc:
        log.error("DNP3 error cliente: %s", exc)
    finally:
        writer.close()
        log.info("DNP3: cliente desconectado %s", addr)


async def _value_updater():
    """Actualiza los valores en el estado compartido."""
    tags = PROTOCOLS["dnp3"]
    while True:
        for tag in tags:
            if tag["unit"] == "bool":
                val = float(int(time.time()) % 30 > 15)  # alterna cada 15s
            else:
                override = state.get_override("dnp3", tag["id"])
                val = get_signal(tag["id"], tag["unit"], override)
            await state.update("dnp3", tag["id"], val)
        await asyncio.sleep(UPDATE_INTERVAL)


async def run():
    log.info("Iniciando servidor DNP3 stub TCP en puerto %d", PORT)
    state.set_status("dnp3", False)
    try:
        server = await asyncio.start_server(_handle_client, "0.0.0.0", PORT)
        state.set_status("dnp3", True)
        log.info("DNP3 stub listo en 0.0.0.0:%d", PORT)
        asyncio.create_task(_value_updater())
        async with server:
            await server.serve_forever()
    except Exception as exc:
        state.set_status("dnp3", False)
        log.error("Error en servidor DNP3: %s", exc)
