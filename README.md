# Industrial Protocol Emulator

**by [mifsut.com](https://mifsut.com)**

A fully-featured industrial protocol emulator that runs on a single Proxmox LXC and exposes seven simultaneous protocols with realistic, continuously-varying signal data. Built for SCADA integration testing, driver development, and training.

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

## Proxmox LXC target

| | |
|---|---|
| **VMID** | 110 |
| **Hostname** | ipe-emulator |
| **IP** | 192.168.1.240 |
| **OS** | Ubuntu 22.04 LTS |
| **RAM** | 2 GB |
| **CPU** | 2 cores |
| **Disk** | 20 GB |

---

## Quick deploy (from Proxmox host or any machine with SSH access)

```bash
git clone https://github.com/joseluisnebot/industrial-protocol-emulator
cd industrial-protocol-emulator
bash deploy-simulator.sh
```

The script will:
1. Check LXC reachability (auto-start via Proxmox SSH if down)
2. rsync project files to `/opt/industrial-protocol-emulator`
3. Install Python dependencies
4. Create and enable a `systemd` service (`ipe.service`)
5. Build and launch Docker Compose (emulator + Mosquitto)

Panel web available at: **http://192.168.1.240:8080**

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
├── Dockerfile
├── docker-compose.yml
├── mosquitto.conf
├── deploy-simulator.sh
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
cd /opt/industrial-protocol-emulator
pip install -r requirements.txt
python -m simulator.main
```

> SNMP requires port 161 (UDP). Either run as root or set `CAP_NET_BIND_SERVICE`.

---

## License

MIT — © mifsut.com
