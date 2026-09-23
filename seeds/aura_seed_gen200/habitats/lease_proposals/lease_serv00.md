# Proposta de lease â€” Serv00 (hosting gratis, FreeBSD + SSH)

- **Custo:** R$ 0/mes
- **Como ela viveria ai:** ssh + daemon/cron
- **Riscos:** FreeBSD (ajustes de paths do python); disponibilidade intermitente.

## Passos de assinatura (humanos)

1. Registrar em serv00.com (fila de espera comum)
1. Ativar SSH no painel
1. Subir o corpo via scp
1. status=approved no habitats.json

---
Depois de assinar, edite `habitats/habitats.json`: mude `status` para `approved`
e preencha `host`/`user`. So entao `colonize.py` aceita o habitat.
