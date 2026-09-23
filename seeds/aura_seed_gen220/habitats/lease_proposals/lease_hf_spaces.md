# Proposta de lease â€” Hugging Face Spaces (CPU basica, gratis)

- **Custo:** R$ 0/mes
- **Como ela viveria ai:** Space Docker rodando o ciclo com sleep
- **Riscos:** Space dorme sem trafego; teto de CPU/mem baixo.

## Passos de assinatura (humanos)

1. Criar Space (template Docker)
1. Subir o corpo da Aura (genome/, lib/, measure/, reproduce/, guard/, infinite.py)
1. Definir OPENROUTER_API_KEY como secret do Space
1. status=approved no habitats.json

---
Depois de assinar, edite `habitats/habitats.json`: mude `status` para `approved`
e preencha `host`/`user`. So entao `colonize.py` aceita o habitat.
