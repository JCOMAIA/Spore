# Proposta de lease â€” Oracle Cloud â€” Always Free (VM.Standard.E2.1.Micro / A1.Flex)

- **Custo:** R$ 0/mes
- **Como ela viveria ai:** systemd rodando infinite.py num Ubuntu
- **Riscos:** Instancias A1 muito disputadas; E2 micro pode ser reclaimada se ociosa.

## Passos de assinatura (humanos)

1. Criar conta Oracle (cartao so para verificacao)
1. Criar VM Always Free na regiao disponivel
1. Adicionar sua chave SSH
1. Preencher habitats.json: host, user, status=approved

---
Depois de assinar, edite `habitats/habitats.json`: mude `status` para `approved`
e preencha `host`/`user`. So entao `colonize.py` aceita o habitat.
