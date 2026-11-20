# © mifsut.com — industrial-protocol-emulator
FROM python:3.11-slim

LABEL maintainer="mifsut.com"
LABEL org.opencontainers.image.source="https://github.com/joseluisnebot/industrial-protocol-emulator"
LABEL org.opencontainers.image.description="Industrial Protocol Emulator - Modbus, OPC-UA, MQTT, BACnet, DNP3, EtherNet/IP, SNMP"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libsnmp-dev \
    mosquitto \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY mosquitto.conf /etc/mosquitto/ipe.conf
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY simulator/ ./simulator/

# 502 Modbus TCP | 4840 OPC-UA | 1883 MQTT (embedded broker) | 47808/udp BACnet/IP
# 20000 DNP3 | 44818 EtherNet/IP | 161/udp SNMP | 8080 web panel
EXPOSE 502 4840 1883 47808/udp 20000 44818 161/udp 8080

# Set MQTT_HOST/MQTT_PORT to use an external broker instead of the embedded one.
ENTRYPOINT ["docker-entrypoint.sh"]
