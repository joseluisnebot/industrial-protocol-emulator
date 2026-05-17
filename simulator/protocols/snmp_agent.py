# © mifsut.com — industrial-protocol-emulator
# snmp_agent.py — Agente SNMP UDP mínimo (v1+v2c, community public, GET/GETNEXT)
#
# Tipos de dato por OID:
#   cpu_load    → Gauge32        (entero sin signo, 0-100)
#   temperatura → Integer32 ×100 (ej: -15.3°C → -1530, 23.5°C → 2350)
#   uptime      → Counter32      (segundos desde arranque del agente)
#
# Factor de escala para temperatura en el SCADA: scale = 0.01

import asyncio
import logging
import struct
import time
from simulator.data_generator import get_signal
from simulator.state import state, PROTOCOLS

log = logging.getLogger("snmp")
PORT = 161
UPDATE_INTERVAL = 2.0

_current_values: dict[str, float] = {}   # valores raw (float, con signo)
_start_time: float = 0.0                  # para el contador uptime


def _build_oids() -> dict[str, tuple]:
    """tag_id → OID tuple desde PROTOCOLS (soporta edición en caliente)."""
    result = {}
    for tag in PROTOCOLS.get("snmp", []):
        oid_str = tag.get("oid", "")
        if oid_str:
            try:
                result[tag["id"]] = tuple(int(x) for x in oid_str.strip().split("."))
            except ValueError:
                log.warning("SNMP: OID inválido para %s: %s", tag["id"], oid_str)
    return result


def _get_tag(tag_id: str) -> dict:
    return next((t for t in PROTOCOLS.get("snmp", []) if t["id"] == tag_id), {})


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

def _enc_gauge32(n: float) -> bytes:
    """Gauge32 (0x42): entero sin signo 32-bit. Trunca negativos a 0."""
    v = max(0, int(n)) & 0xffffffff
    return _tlv(0x42, _enc_uint_bytes(v))

def _enc_counter32(n: float) -> bytes:
    """Counter32 (0x41): contador sin signo 32-bit monotónico."""
    v = max(0, int(n)) & 0xffffffff
    return _tlv(0x41, _enc_uint_bytes(v))

def _enc_integer32(n: float) -> bytes:
    """Integer32 (0x02): entero con signo 32-bit. Soporta negativos."""
    v = max(-2147483648, min(2147483647, int(n)))
    raw = struct.pack('>i', v)
    # Strip redundant leading bytes while preserving sign
    i = 0
    while i < len(raw) - 1:
        if raw[i] == 0x00 and not (raw[i+1] & 0x80): i += 1
        elif raw[i] == 0xFF and (raw[i+1] & 0x80): i += 1
        else: break
    return _tlv(0x02, raw[i:])

def _enc_integer32_x100(n: float) -> bytes:
    """Integer32 ×100: temperatura con 2 decimales. -15.3°C → -1530."""
    return _enc_integer32(round(n * 100))

def _enc_value(tag_id: str, val: float) -> bytes:
    """Selecciona el encoder correcto según el tipo configurado en el tag."""
    tag = _get_tag(tag_id)
    snmp_type = tag.get("snmp_type", "gauge32")
    if snmp_type == "integer32_x100":
        return _enc_integer32_x100(val)
    elif snmp_type == "integer32":
        return _enc_integer32(val)
    elif snmp_type == "counter32":
        return _enc_counter32(val)
    else:
        return _enc_gauge32(val)

def _enc_integer(n: int) -> bytes:
    b = _enc_uint_bytes(abs(n)) if n >= 0 else b'\x00'
    if n >= 0 and (b[0] & 0x80): b = b'\x00' + b
    if n < 0:
        v = struct.pack('>i', max(-2147483648, n))
        b = v.lstrip(b'\xff') or b'\xff'
        if not (b[0] & 0x80): b = b'\xff' + b
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


# ── BER decode helpers ────────────────────────────────────────────────────────

def _read_tlv(data: bytes, offset: int) -> tuple[int, bytes, int]:
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
    i, val = 1, 0
    while i < len(content):
        b = content[i]; i += 1
        val = (val << 7) | (b & 0x7f)
        if not (b & 0x80):
            result.append(val); val = 0
    return tuple(result)


# ── SNMP PDU handler ──────────────────────────────────────────────────────────

def _handle_snmp(data: bytes) -> bytes | None:
    try:
        tag, msg, _ = _read_tlv(data, 0)
        if tag != 0x30: return None
        p = 0
        _, ver_bytes, p = _read_tlv(msg, p)
        version = ver_bytes[0]
        _, community, p = _read_tlv(msg, p)
        if community.decode(errors='replace') != 'public': return None
        pdu_tag, pdu, _ = _read_tlv(msg, p)
        if pdu_tag not in (0xa0, 0xa1): return None

        pp = 0
        _, req_id_bytes, pp = _read_tlv(pdu, pp)
        _, _, pp = _read_tlv(pdu, pp)
        _, _, pp = _read_tlv(pdu, pp)
        _, vbl, pp = _read_tlv(pdu, pp)

        oids = _build_oids()
        sorted_oids = sorted(oids.items(), key=lambda x: x[1])

        resp_varbinds = b''
        vp = 0
        while vp < len(vbl):
            _, vb, vp = _read_tlv(vbl, vp)
            _, oid_bytes, _ = _read_tlv(vb, 0)
            oid_tuple = _parse_oid(oid_bytes)

            if pdu_tag == 0xa1:  # GETNEXT
                next_tid = next((tid for tid, ot in sorted_oids if ot > oid_tuple), None)
                if next_tid:
                    oid_tuple = oids[next_tid]
                    oid_tlv = _enc_oid(oid_tuple)
                    val_tlv = _enc_value(next_tid, _current_values.get(next_tid, 0.0))
                else:
                    oid_tlv = _enc_oid(oid_tuple)
                    val_tlv = _tlv(0x82, b'')  # endOfMibView
            else:  # GET
                tag_id = next((tid for tid, ot in oids.items() if ot == oid_tuple), None)
                oid_tlv = _enc_oid(oid_tuple)
                if tag_id is not None:
                    val_tlv = _enc_value(tag_id, _current_values.get(tag_id, 0.0))
                else:
                    val_tlv = _tlv(0x80, b'')  # noSuchObject

            resp_varbinds += _tlv(0x30, oid_tlv + val_tlv)

        response_pdu = _tlv(0xa2,
            _tlv(0x02, req_id_bytes) +
            _enc_integer(0) +
            _enc_integer(0) +
            _tlv(0x30, resp_varbinds)
        )
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


# ── value updater ─────────────────────────────────────────────────────────────

async def _value_updater():
    while True:
        for tag in PROTOCOLS.get("snmp", []):
            tid = tag["id"]
            snmp_type = tag.get("snmp_type", "gauge32")

            if snmp_type == "counter32":
                # Uptime: segundos transcurridos desde arranque del agente
                val = time.time() - _start_time
            else:
                override = state.get_override("snmp", tid)
                val = get_signal(tid, tag.get("unit", "%"), override)

            await state.update("snmp", tid, val)
            _current_values[tid] = val  # float con signo — el encoder aplica la escala

        await asyncio.sleep(UPDATE_INTERVAL)


async def run():
    global _start_time
    _start_time = time.time()

    log.info("Iniciando agente SNMP en puerto UDP %d", PORT)
    state.set_status("snmp", False)
    try:
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            _SNMPServer,
            local_addr=("0.0.0.0", PORT),
        )
        state.set_status("snmp", True)
        log.info("SNMP listo en UDP 0.0.0.0:%d (v1+v2c, community: public)", PORT)
        log.info("SNMP tipos: cpu_load=Gauge32, temperatura=Integer32×100, uptime=Counter32")
        asyncio.create_task(_value_updater())
        try:
            await asyncio.Future()
        finally:
            transport.close()

    except PermissionError:
        log.error("SNMP: permiso denegado en puerto %d", PORT)
        state.set_status("snmp", False)
    except OSError as exc:
        log.error("SNMP: no se pudo abrir UDP %d: %s", PORT, exc)
        state.set_status("snmp", False)
    except Exception as exc:
        state.set_status("snmp", False)
        log.error("Error en agente SNMP: %s", exc)
