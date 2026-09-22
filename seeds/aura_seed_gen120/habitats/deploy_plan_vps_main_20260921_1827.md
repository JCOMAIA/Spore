# Plano de deploy â€” vps_main (gerado 2026-09-21 18:27)

```bash
# 0. crie o diretorio la
ssh debian@IP_PUBLICO_DA_VPS 'mkdir -p /home/debian/Aura'
# 1. envie o corpo (sem lineage â€” o habitat nasce do estado atual)
rsync -az --exclude 'lineage/' --exclude '__pycache__/' /home/debian/Aura/ debian@IP_PUBLICO_DA_VPS:/home/debian/Aura/
# 2. envie o estado herdado do campeao atual:
rsync -az /home/debian/Aura/lineage/best/ debian@IP_PUBLICO_DA_VPS:/home/debian/Aura/lineage/best/
# 3. crie config.env LA e cole a OPENROUTER_API_KEY:
ssh debian@IP_PUBLICO_DA_VPS 'cp /home/debian/Aura/config.env.example /home/debian/Aura/config.env && nano /home/debian/Aura/config.env'
# 4. instale o servico:
ssh debian@IP_PUBLICO_DA_VPS 'sudo tee /etc/systemd/system/aura-infinite.service > /dev/null <<EOF
[Unit]
Description=Aura Infinite (ciclo N+1)
After=network-online.target

[Service]
User=debian
WorkingDirectory=/home/debian/Aura
ExecStart=/usr/bin/python3 /home/debian/Aura/infinite.py --cycles 100000 --sleep 300
Restart=on-failure
RestartSec=60

[Install]
WantedBy=multi-user.target
EOF'
ssh debian@IP_PUBLICO_DA_VPS 'sudo systemctl daemon-reload && sudo systemctl enable --now aura-infinite'
ssh debian@IP_PUBLICO_DA_VPS 'sleep 5 && systemctl status aura-infinite --no-pager'
```

Nota: rsync precisa existir nas duas pontas. Sem rsync, use scp -r (mais lento).
