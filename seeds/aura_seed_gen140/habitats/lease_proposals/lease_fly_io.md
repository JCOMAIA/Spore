# Proposta de lease â€” Fly.io (free allowance)

- **Custo:** USD 0 dentro da franquia
- **Como ela viveria ai:** fly launch + maquina compartilhada
- **Riscos:** Franquia muda com o tempo; cartao pode ser exigido.

## Passos de assinatura (humanos)

1. Criar conta fly.io
1. fly launch no diretorio do corpo
1. Definir secret da API key
1. status=approved no habitats.json

---
Depois de assinar, edite `habitats/habitats.json`: mude `status` para `approved`
e preencha `host`/`user`. So entao `colonize.py` aceita o habitat.
