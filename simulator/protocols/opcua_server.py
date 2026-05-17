# © mifsut.com — industrial-protocol-emulator
# opcua_server.py — Servidor OPC-UA en puerto 4840

import asyncio
import logging
from asyncua import Server
from asyncua import ua
from simulator.data_generator import get_signal
from simulator.state import state, PROTOCOLS

log = logging.getLogger("opcua")
PORT = 4840
UPDATE_INTERVAL = 1.0


async def run():
    log.info("Iniciando servidor OPC-UA en puerto %d", PORT)
    state.set_status("opcua", False)
    try:
        server = Server()
        await server.init()
        server.set_endpoint(f"opc.tcp://0.0.0.0:{PORT}/emulator/")
        server.set_server_name("mifsut.com Industrial Emulator")

        # Namespace
        uri = "https://mifsut.com/emulator"
        idx = await server.register_namespace(uri)

        # Nodos
        objects = server.get_objects_node()
        motor = await objects.add_object(idx, "Motor")
        temp_obj = await objects.add_object(idx, "Temp")

        node_map = {}
        tags = PROTOCOLS["opcua"]
        for tag in tags:
            node_id_str = tag["node_id"]  # e.g. "ns=2;s=Motor/Speed"
            parts = node_id_str.split(";s=", 1)
            path = parts[1] if len(parts) > 1 else tag["id"]
            folder, name = (path.split("/", 1) + [path])[:2] if "/" in path else ("Root", path)
            parent = motor if "Motor" in folder else temp_obj
            node = await parent.add_variable(idx, name, 0.0)
            await node.set_writable()
            node_map[tag["id"]] = node

        state.set_status("opcua", True)
        log.info("OPC-UA listo en opc.tcp://0.0.0.0:%d", PORT)

        async with server:
            while True:
                for tag in tags:
                    override = state.get_override("opcua", tag["id"])
                    val = get_signal(tag["id"], tag["unit"], override)
                    await state.update("opcua", tag["id"], val)
                    if tag["id"] in node_map:
                        await node_map[tag["id"]].write_value(val)
                await asyncio.sleep(UPDATE_INTERVAL)
    except Exception as exc:
        state.set_status("opcua", False)
        log.error("Error en servidor OPC-UA: %s", exc)
