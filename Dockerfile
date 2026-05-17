# © mifsut.com — industrial-protocol-emulator
FROM python:3.11-slim

LABEL maintainer="mifsut.com"
LABEL description="Industrial Protocol Emulator — Modbus, OPC-UA, MQTT, BACnet, DNP3, EtherNet/IP, SNMP"

WORKDIR /app

# Dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libsnmp-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY simulator/ ./simulator/

# Puertos expuestos
# 502   Modbus TCP
# 4840  OPC-UA
# 1883  MQTT (broker externo — el contenedor no lo expone)
# 47808 BACnet/IP UDP
# 20000 DNP3 TCP
# 44818 EtherNet/IP TCP
# 161   SNMP UDP
# 8080  Panel web

EXPOSE 502 4840 47808/udp 20000 44818 8080

# SNMP necesita UDP 161 — requiere privilegios o capabilities
# En Docker: usar --cap-add=NET_BIND_SERVICE o mapear a puerto >1024

CMD ["python", "-m", "simulator.main"]
