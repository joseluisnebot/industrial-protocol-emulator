# © mifsut.com — industrial-protocol-emulator
# state.py — Estado compartido entre todos los servidores de protocolo y la web UI

import asyncio
import time
from dataclasses import dataclass, field
from simulator import config as _cfg

# PROTOCOLS se carga desde JSON (o defaults si no existe el fichero).
# Es un dict mutable — los servidores lo leen al arrancar cada `run()`.
PROTOCOLS: dict[str, list[dict]] = _cfg.load()


def reload_protocols(new_protocols: dict):
    """Actualiza PROTOCOLS in-place y persiste en disco."""
    PROTOCOLS.clear()
    PROTOCOLS.update(new_protocols)
    _cfg.save(new_protocols)


# ── Estado en tiempo real ──────────────────────────────────────────────────────

@dataclass
class TagState:
    value: float = 0.0
    unit: str = ""
    ts: float = field(default_factory=time.time)
    override: dict | None = None


class SimulatorState:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._values: dict[str, dict[str, TagState]] = {}
        self._server_status: dict[str, bool] = {}
        self._subscribers: list[asyncio.Queue] = []
        self._init_from_protocols()

    def _init_from_protocols(self):
        for proto, tags in PROTOCOLS.items():
            if proto not in self._values:
                self._values[proto] = {}
            for tag in tags:
                tid = tag["id"]
                if tid not in self._values[proto]:
                    self._values[proto][tid] = TagState(unit=tag.get("unit", ""))
            if proto not in self._server_status:
                self._server_status[proto] = False

    def reinit_protocol(self, protocol: str):
        """Reinicializa el estado de un protocolo tras cambio de tags."""
        tags = PROTOCOLS.get(protocol, [])
        self._values[protocol] = {
            tag["id"]: TagState(unit=tag.get("unit", "")) for tag in tags
        }
        self._server_status[protocol] = False

    async def update(self, protocol: str, tag_id: str, value: float):
        async with self._lock:
            if protocol not in self._values:
                self._values[protocol] = {}
            if tag_id not in self._values[protocol]:
                unit = next(
                    (t.get("unit", "") for t in PROTOCOLS.get(protocol, []) if t["id"] == tag_id),
                    ""
                )
                self._values[protocol][tag_id] = TagState(unit=unit)
            self._values[protocol][tag_id].value = value
            self._values[protocol][tag_id].ts = time.time()
        unit = self._values[protocol][tag_id].unit
        await self._notify(protocol, tag_id, value, unit)

    async def set_override(self, protocol: str, tag_id: str, override: dict | None):
        async with self._lock:
            if protocol in self._values and tag_id in self._values[protocol]:
                self._values[protocol][tag_id].override = override

    def get_override(self, protocol: str, tag_id: str) -> dict | None:
        return self._values.get(protocol, {}).get(tag_id, TagState()).override

    def snapshot(self) -> dict:
        result = {}
        for proto, tags in self._values.items():
            result[proto] = {
                "online": self._server_status.get(proto, False),
                "tags": {
                    tid: {"value": ts.value, "unit": ts.unit, "ts": ts.ts, "override": ts.override}
                    for tid, ts in tags.items()
                },
            }
        return result

    def set_status(self, protocol: str, online: bool):
        self._server_status[protocol] = online

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    async def _notify(self, protocol: str, tag_id: str, value: float, unit: str = ""):
        msg = {"protocol": protocol, "tag_id": tag_id, "value": value, "unit": unit, "ts": time.time()}
        for q in list(self._subscribers):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass


state = SimulatorState()
