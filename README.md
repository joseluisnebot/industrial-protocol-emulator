# Industrial Protocol Emulator

**by [mifsut.com](https://mifsut.com)**

An industrial protocol emulator that runs in one container and exposes seven simultaneous protocols with realistic, continuously-varying signal data. Built for SCADA integration testing, driver development, and training.

---

## Protocols emulated

| Protocol | Port | Transport | Library |
|---|---|---|---|
| Modbus TCP | **502** | TCP | pymodbus 3.6 |
| OPC-UA | **4840** | TCP | asyncua |
| MQTT | **1883** | TCP | paho-mqtt + Mosquitto |
| BACnet/IP | **47808** | UDP | bacpypes3 |
| DNP3 | **20000** | TCP | custom stub (Group 30 Var 5) |
| EtherNet/IP (CIP) | **44818** | TCP | cpppo / minimal fallback |
| SNMP | **161** | UDP | pysnmp (v1 + v2c, community: public) |
| **Web panel** | **8080** | HTTP/WS | FastAPI + WebSocket |

---

## Quick start

```bash
git clone https://github.com/joseluisnebot/industrial-protocol-emulator
cd industrial-protocol-emulator
docker compose up -d
```

Open the panel at **http://localhost:8080**. The compose file starts the emulator and a Mosquitto broker (host networking, needed for SNMP/BACnet UDP).

A prebuilt image is published to `ghcr.io/joseluisnebot/industrial-protocol-emulator:latest` (built by GitHub Actions on every push to `main`). It needs an MQTT broker; point it with `MQTT_HOST` / `MQTT_PORT`:

```bash
docker run --rm --network host --cap-add NET_BIND_SERVICE \
  -e MQTT_HOST=localhost ghcr.io/joseluisnebot/industrial-protocol-emulator:latest
```

## Honest limitations

- **DNP3** is a minimal stub: it answers Class 0 / integrity polls for analog inputs only (Group 30 Var 5).
- **EtherNet/IP** is a basic server (via `cpppo`, with a minimal fallback). Check it against your driver before relying on it.
- **SNMP** supports v1 and v2c only, community `public`. No SNMPv3.
- No authentication or TLS on any protocol or on the web panel. **Run it in a lab network, never exposed to the internet.**
- Signals are synthetic (sine, ramp, random walk, constant). It does not model a real process.

---

## Web panel features

- **Live tag values** — all protocols and tags update in real time via WebSocket
- **Signal override** — for any tag, set custom range + pattern (sine / ramp / random / constant)
- **YAML generator** — generate ready-to-paste SCADA device config for any protocol
- **Status badges** — green/red per protocol (binding failed, lib missing, etc.)

---

## Signal patterns

| Pattern | Description |
|---|---|
| `sine` | Sinusoidal within the tag's range |
| `ramp` | Linear ramp, resets at max |
| `random` | Bounded random walk |
| `constant` | Fixed mid-range value |

Each tag has industrial-realistic default ranges (e.g., Hz: 0–60, °C: -20–150, V: 200–480).

---

## Project structure

```
industrial-protocol-emulator/
├── simulator/
│   ├── main.py                  # asyncio orchestrator
│   ├── state.py                 # shared state + WebSocket pub/sub
│   ├── data_generator.py        # signal generators
│   ├── protocols/
│   │   ├── modbus_server.py
│   │   ├── opcua_server.py
│   │   ├── mqtt_publisher.py
│   │   ├── bacnet_server.py
│   │   ├── dnp3_server.py
│   │   ├── ethernetip_server.py
│   │   └── snmp_agent.py
│   └── web/
│       ├── app.py               # FastAPI REST + WebSocket
│       └── static/index.html    # single-page UI
├── devices-simulator/           # ready-to-paste SCADA YAML configs
│   ├── modbus/emulator-modbus.yaml
│   ├── opcua/emulator-opcua.yaml
│   ├── mqtt_ext/emulator-mqtt.yaml
│   ├── bacnet/emulator-bacnet.yaml
│   ├── dnp3/emulator-dnp3.yaml
│   ├── ethernet_ip/emulator-eip.yaml
│   └── snmp/emulator-snmp.yaml
├── requirements.txt
├── LICENSE
├── Dockerfile
├── docker-compose.yml
├── mosquitto.conf
└── README.md
```

---

## REST API

```
GET  /api/state                          # full snapshot
GET  /api/protocols                      # tag definitions per protocol
POST /api/override/{protocol}/{tag_id}   # body: {"min":0,"max":100,"pattern":"sine"}
                                         # empty body {} → reset to auto
GET  /api/yaml/{protocol}?host=IP        # generate SCADA YAML
WS   /ws                                 # real-time updates
```

---

## Manual start (without Docker)

```bash
pip install -r requirements.txt
MQTT_HOST=localhost python -m simulator.main
```

> SNMP uses UDP port 161. Run as root or set `CAP_NET_BIND_SERVICE`.

---

## Part of a bigger story

Many small makers of connected industrial equipment will need to comply with the EU Cyber Resilience Act. Test your drivers here, then check where your product stands with the free classifier at [mifsut.com/cra](https://mifsut.com/cra).

## License

MIT, see [LICENSE](LICENSE). © mifsut.com
