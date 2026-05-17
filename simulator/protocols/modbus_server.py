# © mifsut.com — industrial-protocol-emulator
# modbus_server.py — Servidor Modbus TCP en puerto 502

import asyncio
import logging
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSlaveContext, ModbusServerContext
from pymodbus.server import StartAsyncTcpServer
from pymodbus.device import ModbusDeviceIdentification
from simulator.data_generator import get_signal
from simulator.state import state, PROTOCOLS

log = logging.getLogger("modbus")
PORT = 502
UPDATE_INTERVAL = 1.0


def _float_to_registers(value: float) -> list[int]:
    """Convierte float a dos registros Modbus de 16 bits."""
    import struct
    raw = struct.pack(">f", float(value))
    hi, lo = struct.unpack(">HH", raw)
    return [hi, lo]


async def _updater(context: ModbusServerContext):
    """Actualiza los registros holding con valores generados."""
    tags = PROTOCOLS["modbus"]
    while True:
        for tag in tags:
            override = state.get_override("modbus", tag["id"])
            val = get_signal(tag["id"], tag["unit"], override)
            await state.update("modbus", tag["id"], val)
            # Guardar en registros holding (address - 40001 = índice)
            idx = tag["address"] - 40001
            regs = _float_to_registers(val / tag.get("scale", 1))
            slave = context[0x00]
            slave.setValues(3, idx, regs)
        await asyncio.sleep(UPDATE_INTERVAL)


async def run():
    log.info("Iniciando servidor Modbus TCP en puerto %d", PORT)
    state.set_status("modbus", False)
    try:
        store = ModbusSlaveContext(
            hr=ModbusSequentialDataBlock(0, [0] * 200),
            ir=ModbusSequentialDataBlock(0, [0] * 200),
        )
        context = ModbusServerContext(slaves=store, single=True)

        identity = ModbusDeviceIdentification(
            info_name={
                "VendorName": "mifsut.com",
                "ProductCode": "IPE-MODBUS",
                "VendorUrl": "https://mifsut.com",
                "ProductName": "Industrial Protocol Emulator",
                "ModelName": "Emulated VFD",
            }
        )

        state.set_status("modbus", True)
        log.info("Modbus TCP listo en 0.0.0.0:%d", PORT)

        # Lanzar el updater en paralelo
        asyncio.create_task(_updater(context))

        await StartAsyncTcpServer(context=context, identity=identity, address=("0.0.0.0", PORT))
    except Exception as exc:
        state.set_status("modbus", False)
        log.error("Error en servidor Modbus: %s", exc)
