# © mifsut.com — industrial-protocol-emulator
# bacnet_server.py — Servidor BACnet/IP en puerto UDP 47808

import asyncio
import logging
from simulator.data_generator import get_signal
from simulator.state import state, PROTOCOLS

log = logging.getLogger("bacnet")
DEVICE_ID = 999
DEVICE_NAME = "EMULATOR-BACNET"
UPDATE_INTERVAL = 1.0

# Mapeo de unidades de texto a BACnet Engineering Units integer
_UNIT_MAP = {
    "°C": 62,    # degrees-celsius
    "°F": 64,    # degrees-fahrenheit
    "K":  63,    # degrees-kelvin
    "bar": 55,   # bars
    "Pa": 53,    # pascals
    "kPa": 54,   # kilopascals
    "psi": 56,   # pounds-force-per-square-inch
    "m3/h": 119, # cubic-meters-per-hour
    "L/s": 92,   # liters-per-second
    "%": 98,     # percent
    "Hz": 27,    # hertz
    "A": 2,      # amperes
    "V": 5,      # volts
    "kW": 48,    # kilowatts
    "kWh": 19,   # kilowatt-hours
    "rpm": 104,  # revolutions-per-minute
    "s": 73,     # seconds
}


async def run():
    log.info("Iniciando servidor BACnet/IP — Device ID=%d", DEVICE_ID)
    state.set_status("bacnet", False)
    try:
        from bacpypes3.app import Application
        from bacpypes3.local.analog import AnalogInputObject
        from bacpypes3.local.device import DeviceObject
        from bacpypes3.pdu import Address
        from bacpypes3.primitivedata import Real

        device = DeviceObject(
            objectIdentifier=("device", DEVICE_ID),
            objectName=DEVICE_NAME,
            description="mifsut.com Industrial Protocol Emulator",
            vendorName="mifsut.com",
            vendorIdentifier=9999,
        )

        app = Application(device, Address("0.0.0.0"))

        # Crear Analog Input objects
        ai_objects = {}
        tags = PROTOCOLS["bacnet"]
        for i, tag in enumerate(tags, start=1):
            unit_int = _UNIT_MAP.get(tag["unit"], 95)  # 95 = no-units
            ai = AnalogInputObject(
                objectIdentifier=("analogInput", i),
                objectName=tag["id"],
                presentValue=Real(0.0),
                units=unit_int,
                description=f"Emulated {tag['id']}",
            )
            app.add_object(ai)
            ai_objects[tag["id"]] = ai

        state.set_status("bacnet", True)
        log.info("BACnet/IP listo — Device %d en UDP 0.0.0.0:47808", DEVICE_ID)

        while True:
            for tag in tags:
                override = state.get_override("bacnet", tag["id"])
                val = get_signal(tag["id"], tag["unit"], override)
                await state.update("bacnet", tag["id"], val)
                if tag["id"] in ai_objects:
                    ai_objects[tag["id"]].presentValue = Real(val)
            await asyncio.sleep(UPDATE_INTERVAL)

    except ImportError:
        log.warning("bacpypes3 no disponible — servidor BACnet desactivado")
        state.set_status("bacnet", False)
    except Exception as exc:
        state.set_status("bacnet", False)
        log.error("Error en servidor BACnet: %s", exc)
