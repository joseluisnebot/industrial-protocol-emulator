#!/bin/sh
# Start the embedded Mosquitto broker unless an external one is configured.
# Set MQTT_HOST to point at your own broker (the embedded one is then skipped).
set -e
if [ -z "$MQTT_HOST" ] || [ "$MQTT_HOST" = "localhost" ] || [ "$MQTT_HOST" = "127.0.0.1" ]; then
  mosquitto -c /etc/mosquitto/ipe.conf -d
  export MQTT_HOST=localhost
fi
exec python -m simulator.main
