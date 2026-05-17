# © mifsut.com — industrial-protocol-emulator
# snmp_agent.py — Agente SNMP UDP mínimo (v1+v2c, community public, GET/GETNEXT)
#
# Implementación custom asyncio — no depende de pysnmp para evitar conflictos
# con su event loop interno. Soporta: GetRequest (0xa0), GetNextRequest (0xa1).
# OIDs registrados: cpu_load, temperatura, uptime (enterprise 1.3.6.1.4.1.9999)

import asyncio
import logging
from simulator.data_generator import get_signal
from simulator.state import state, PROTOCOLS

log = logging.getLogger("snmp")
PORT = 161
UPDATE_INTERVAL = 2.0

_current_values: dict[str, int] = {}


def _build_oids() -> dict[str, tuple]:
    """Construye el mapa tag_id → OID tuple desde PROTOCOLS (soporta edición en caliente)."""
    result = {}
    for tag in PROTOCOLS.get("snmp", []):
        oid_str = tag.get("oid", "")
        if oid_str:
            try:
                result[tag["id"]] = tuple(int(x) for x in oid_str.strip().split("."))
            except ValueError:
                log.warning("SNMP: OID inválido para %s: %s", tag["id"], oid_str)
    return result


# ── BER encode helpers ────────────────────────────────────────────────────────

def _enc_len(n: int) -> bytes:
    if n < 0x80: return bytes([n])
    if n < 0x100: return bytes([0x81, n])
    return bytes([0x82, n >> 8, n & 0xff])

def _tlv(tag: int, content: bytes) -> bytes:
    return bytes([tag]) + _enc_len(len(content)) + content

def _enc_uint_bytes(n: int) -> bytes:
    if n == 0: return b'\x00'
    b = []
    while n:
        b.append(n & 0xff)
        n >>= 8
    return bytes(reversed(b))

def _enc_integer(n: int) -> bytes:
    b = _enc_uint_bytes(n)
    if b[0] & 0x80: b = b'\x00' + b  # positive sign byte
    return _tlv(0x02, b)

def _enc_octet(s: str | bytes) -> bytes:
    if isinstance(s, str): s = s.encode()
    return _tlv(0x04, s)

def _enc_oid_component(n: int) -> bytes:
    if n < 128: return bytes([n])
    parts = []
    while n:
        parts.append(n & 0x7f)
        n >>= 7
    parts.reverse()
    return bytes([p | 0x80 for p in parts[:-1]] + [parts[-1]])

def _enc_oid(oid: tuple) -> bytes:
    content = _enc_oid_component(40 * oid[0] + oid[1])
    for c in oid[2:]:
        content += _enc_oid_component(c)
    return _tlv(0x06, content)

def _enc_gauge32(n: int) -> bytes:
    n = max(0, int(n)) & 0xffffffff
    return _tlv(0x42, _enc_uint_bytes(n))  # APPLICATION [2] = Gauge32


# ── BER decode helpers ────────────────────────────────────────────────────────

def _read_tlv(data: bytes, offset: int) -> tuple[int, bytes, int]:
    """Return (tag, content, next_offset)."""
    tag = data[offset]; offset += 1
    b = data[offset]
    if b < 0x80:
        length = b; offset += 1
    elif b == 0x81:
        length = data[offset + 1]; offset += 2
    elif b == 0x82:
        length = (data[offset + 1] << 8) | data[offset + 2]; offset += 3
    else:
        raise ValueError(f"unsupported BER length byte: {b:#x}")
    return tag, data[offset:offset + length], offset + length

def _parse_oid(content: bytes) -> tuple:
    result = [content[0] // 40, content[0] % 40]
    i, val, building = 1, 0, False
    while i < len(content):
        b = content[i]; i += 1
        val = (val << 7) | (b & 0x7f)
        if not (b & 0x80):
            result.append(val); val = 0
    return tuple(result)


# ── SNMP PDU handler ──────────────────────────────────────────────────────────

def _handle_snmp(data: bytes) -> bytes | None:
    """Parse GET/GETNEXT, return encoded GET-RESPONSE or None."""
    try:
        # Outer SEQUENCE
        tag, msg, _ = _read_tlv(data, 0)
        if tag != 0x30: return None
        p = 0
        # version
        _, ver_bytes, p = _read_tlv(msg, p)
        version = ver_bytes[0]
        # community
        _, community, p = _read_tlv(msg, p)
        if community.decode(errors='replace') != 'public': return None
        # PDU tag
        pdu_tag, pdu, _ = _read_tlv(msg, p)
        if pdu_tag not in (0xa0, 0xa1): return None  # only GET and GETNEXT

        pp = 0
        _, req_id_bytes, pp = _read_tlv(pdu, pp)   # request-id (raw content)
        _, _, pp = _read_tlv(pdu, pp)               # error-status (ignored)
        _, _, pp = _read_tlv(pdu, pp)               # error-index (ignored)
        _, vbl, pp = _read_tlv(pdu, pp)             # varbind list

        # OIDs frescos desde config (soporta edición en caliente)
        oids = _build_oids()
        sorted_oids = sorted(oids.items(), key=lambda x: x[1])

        # Build response varbinds
        resp_varbinds = b''
        vp = 0
        while vp < len(vbl):
            _, vb, vp = _read_tlv(vbl, vp)
            _, oid_bytes, _ = _read_tlv(vb, 0)
            oid_tuple = _parse_oid(oid_bytes)

            if pdu_tag == 0xa1:  # GETNEXT: find next lexicographic OID
                next_tid = next(
                    (tid for tid, ot in sorted_oids if ot > oid_tuple), None
                )
                if next_tid:
                    oid_tuple = oids[next_tid]
                    oid_tlv = _enc_oid(oid_tuple)
                    val_tlv = _enc_gauge32(_current_values.get(next_tid, 0))
                else:
                    oid_tlv = _enc_oid(oid_tuple)
                    val_tlv = _tlv(0x82, b'')  # endOfMibView
            else:  # GET: exact match
                tag_id = next((tid for tid, ot in oids.items() if ot == oid_tuple), None)
                oid_tlv = _enc_oid(oid_tuple)
                if tag_id and tag_id in _current_values:
                    val_tlv = _enc_gauge32(_current_values[tag_id])
                else:
                    val_tlv = _tlv(0x80, b'')  # noSuchObject

            resp_varbinds += _tlv(0x30, oid_tlv + val_tlv)

        # Assemble GetResponse PDU (0xa2)
        response_pdu = _tlv(0xa2,
            _tlv(0x02, req_id_bytes) +  # request-id (copy raw content)
            _enc_integer(0) +            # error-status: noError
            _enc_integer(0) +            # error-index: 0
            _tlv(0x30, resp_varbinds)
        )

        # Assemble SNMP message
        message = _enc_integer(version) + _enc_octet('public') + response_pdu
        return _tlv(0x30, message)

    except Exception as exc:
        log.debug("SNMP PDU parse error: %s", exc)
        return None


# ── asyncio UDP protocol ──────────────────────────────────────────────────────

class _SNMPServer(asyncio.DatagramProtocol):
    def connection_made(self, transport):
        self._transport = transport

    def datagram_received(self, data: bytes, addr):
        response = _handle_snmp(data)
        if response:
            self._transport.sendto(response, addr)
        else:
            log.debug("SNMP: ignorando paquete de %s", addr)


# ── value updater + main entry ────────────────────────────────────────────────

async def _value_updater():
    while True:
        for tag in PROTOCOLS.get("snmp", []):  # lee config viva
            override = state.get_override("snmp", tag["id"])
            val = get_signal(tag["id"], tag.get("unit", "%"), override)
            await state.update("snmp", tag["id"], val)
            _current_values[tag["id"]] = int(abs(val))
        await asyncio.sleep(UPDATE_INTERVAL)


async def run():
    log.info("Iniciando agente SNMP en puerto UDP %d", PORT)
    state.set_status("snmp", False)
    try:
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            _SNMPServer,
            local_addr=("0.0.0.0", PORT),
        )
        state.set_status("snmp", True)
        log.info("SNMP agente listo en UDP 0.0.0.0:%d (v1+v2c, community: public)", PORT)
        asyncio.create_task(_value_updater())
        try:
            await asyncio.Future()  # run forever
        finally:
            transport.close()

    except PermissionError:
        log.error("SNMP: permiso denegado en puerto %d — necesita root o CAP_NET_BIND_SERVICE", PORT)
        state.set_status("snmp", False)
    except OSError as exc:
        log.error("SNMP: no se pudo abrir UDP %d: %s", PORT, exc)
        state.set_status("snmp", False)
    except Exception as exc:
        state.set_status("snmp", False)
        log.error("Error en agente SNMP: %s", exc)
