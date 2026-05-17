#!/usr/bin/env bash
# © mifsut.com — industrial-protocol-emulator
# deploy-simulator.sh — Despliega el emulador en el LXC de Proxmox (VMID 110, IP 192.168.1.240)
set -euo pipefail

LXC_IP="192.168.1.240"
LXC_USER="root"
REMOTE_DIR="/opt/industrial-protocol-emulator"
PROXMOX_IP="192.168.1.111"
VMID=110

echo "============================================"
echo "  Industrial Protocol Emulator — Deploy"
echo "  mifsut.com"
echo "============================================"

# ── 1. Verificar conectividad ────────────────────────────────────────────────
echo "[1/5] Verificando conectividad con LXC ($LXC_IP)..."
if ! ping -c 1 -W 2 "$LXC_IP" &>/dev/null; then
  echo "  El LXC no responde. Intentando arrancar desde Proxmox..."
  ssh -i /root/.ssh/proxmox -o StrictHostKeyChecking=no root@"$PROXMOX_IP" \
    "pct start $VMID || true"
  sleep 8
  ping -c 1 -W 5 "$LXC_IP" || { echo "ERROR: LXC no accesible"; exit 1; }
fi
echo "  OK — LXC responde en $LXC_IP"

# ── 2. Copiar ficheros ────────────────────────────────────────────────────────
echo "[2/5] Copiando ficheros al LXC..."
ssh -o StrictHostKeyChecking=no "$LXC_USER@$LXC_IP" "mkdir -p $REMOTE_DIR"
rsync -az --exclude '__pycache__' --exclude '*.pyc' --exclude '.git' \
  ./ "$LXC_USER@$LXC_IP:$REMOTE_DIR/"
echo "  OK — ficheros copiados"

# ── 3. Instalar dependencias ──────────────────────────────────────────────────
echo "[3/5] Instalando dependencias Python..."
ssh "$LXC_USER@$LXC_IP" bash <<'ENDSSH'
  cd /opt/industrial-protocol-emulator
  python3 -m pip install --quiet -r requirements.txt 2>&1 | tail -5
ENDSSH
echo "  OK — dependencias instaladas"

# ── 4. Instalar servicio systemd ──────────────────────────────────────────────
echo "[4/5] Configurando servicio systemd..."
ssh "$LXC_USER@$LXC_IP" bash <<'ENDSSH'
cat > /etc/systemd/system/ipe.service <<'EOF'
[Unit]
Description=Industrial Protocol Emulator (mifsut.com)
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=/opt/industrial-protocol-emulator
ExecStart=/usr/bin/docker compose up
ExecStop=/usr/bin/docker compose down
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable ipe
ENDSSH
echo "  OK — servicio systemd configurado"

# ── 5. Iniciar ────────────────────────────────────────────────────────────────
echo "[5/5] Iniciando emulador..."
ssh "$LXC_USER@$LXC_IP" bash <<'ENDSSH'
  cd /opt/industrial-protocol-emulator
  docker compose down 2>/dev/null || true
  docker compose build --quiet
  docker compose up -d
  sleep 3
  docker compose ps
ENDSSH

echo ""
echo "============================================"
echo "  Deploy completado!"
echo "  Panel web: http://$LXC_IP:8080"
echo "  Protocolos:"
echo "    Modbus TCP:    $LXC_IP:502"
echo "    OPC-UA:        opc.tcp://$LXC_IP:4840"
echo "    MQTT:          $LXC_IP:1883"
echo "    BACnet/IP:     $LXC_IP:47808 (UDP)"
echo "    DNP3:          $LXC_IP:20000"
echo "    EtherNet/IP:   $LXC_IP:44818"
echo "    SNMP:          $LXC_IP:161 (UDP, community: public)"
echo "============================================"
