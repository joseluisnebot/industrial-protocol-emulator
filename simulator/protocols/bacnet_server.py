# © mifsut.com — industrial-protocol-emulator
# bacnet_server.py — Servidor BACnet/IP en puerto UDP 47808

import asyncio
import logging
from bacpypes3.app import Application
from bacpypes3.local.analog import AnalogInputObject
from bacpypes3.local.device import DeviceObject
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import Real
from simulator.data_generator import get_signal
from simulator.state import state, PROTOCOLS

log = logging.getLogger("bacnet")
DEVICE_ID = 999
DEVICE_NAME = "EMULATOR-BACNET"
UPDATE_INTERVAL = 1.0


async def run():
    log.info("Iniciando servidor BACnet/IP — Device ID=%d", DEVICE_ID)
    state.set_status("bacnet", False)
    try:
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
            ai = AnalogInputObject(
                objectIdentifier=("analogInput", i),
                objectName=tag["id"],
                presentValue=Real(0.0),
                units=tag["unit"],
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
