# © mifsut.com — industrial-protocol-emulator
# snmp_agent.py — Agente SNMP en puerto UDP 161

import asyncio
import logging
from simulator.data_generator import get_signal
from simulator.state import state, PROTOCOLS

log = logging.getLogger("snmp")
PORT = 161
UPDATE_INTERVAL = 2.0

# OIDs del emulador (enterprise: 1.3.6.1.4.1.9999)
OIDS = {
    "cpu_load":    (1, 3, 6, 1, 4, 1, 9999, 1, 1, 0),
    "temperatura": (1, 3, 6, 1, 4, 1, 9999, 1, 2, 0),
    "uptime":      (1, 3, 6, 1, 4, 1, 9999, 1, 3, 0),
}


async def run():
    log.info("Iniciando agente SNMP en puerto UDP %d", PORT)
    state.set_status("snmp", False)
    try:
        # Lazy imports — pysnmp-lextudio o pysnmp clásico
        from pysnmp.entity import engine, config
        from pysnmp.entity.rfc3413 import cmdrsp, context
        from pysnmp.carrier.asyncio.dgram import udp
        from pysnmp.proto import rfc1902

        snmp_engine = engine.SnmpEngine()

        config.addTransport(
            snmp_engine,
            udp.domainName,
            udp.UdpTransport().openServerMode(("0.0.0.0", PORT)),
        )
        config.addV1System(snmp_engine, "read-area", "public")

        snmp_context = context.SnmpContext(snmp_engine)
        mib_builder = snmp_context.getMibInstrum().getMibBuilder()

        MibScalarInstance, = mib_builder.importSymbols("SNMPv2-SMI", "MibScalarInstance")
        mib_objects = {}
        tags = PROTOCOLS["snmp"]
        for tag in tags:
            oid = OIDS.get(tag["id"])
            if oid:
                obj = MibScalarInstance(oid[:-1], (oid[-1],), rfc1902.Gauge32(0))
                mib_objects[tag["id"]] = obj

        mib_builder.exportSymbols("__MY_MIB__", **{k: v for k, v in mib_objects.items()})

        cmdrsp.GetCommandResponder(snmp_engine, snmp_context)
        cmdrsp.NextCommandResponder(snmp_engine, snmp_context)
        cmdrsp.BulkCommandResponder(snmp_engine, snmp_context)

        state.set_status("snmp", True)
        log.info("SNMP agente listo en UDP 0.0.0.0:%d (community: public)", PORT)

        while True:
            for tag in tags:
                override = state.get_override("snmp", tag["id"])
                val = get_signal(tag["id"], tag["unit"], override)
                await state.update("snmp", tag["id"], val)
                if tag["id"] in mib_objects:
                    mib_objects[tag["id"]].syntax = rfc1902.Gauge32(int(abs(val)))
            await asyncio.sleep(UPDATE_INTERVAL)

    except PermissionError:
        log.error("SNMP: permiso denegado en puerto %d — ejecutar como root o usar puerto >1024", PORT)
        state.set_status("snmp", False)
    except ImportError as exc:
        log.warning("pysnmp no disponible (%s) — agente SNMP desactivado", exc)
        state.set_status("snmp", False)
    except Exception as exc:
        state.set_status("snmp", False)
        log.error("Error en agente SNMP: %s", exc)
