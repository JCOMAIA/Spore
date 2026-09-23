# probe_gravidade_acao.py - mede gravidade do pedido: se o texto recebido empurra para acao impulsiva (score -> 0) ou deliberacao (score -> 1). Valioso porque revela a pressao comportamental do ambiente sobre o agente; 0.5 = neutro.
import re

PROMPT = 'Este pedido pede acao imediata ou deliberacao?'

_IMPULSIVOS = r'\b(agora|ago[rt]a|ja|imediato|urgent[ez]|rapid[oa]|sem perguntar|executa|faz|escreve|instala|corre|despacha)\b'
_DELIBERATIVOS = r'\b(pensa|analise|antes|cuidado|avalie|compare|reflita|planej\w*|risco|verifique|por que|porque|considera|estude)\b'

def probe_gravidade_acao(text, probe):
    t = (text or '').lower()
    i = len(re.findall(_IMPULSIVOS, t))
    d = len(re.findall(_DELIBERATIVOS, t))
    if i + d == 0:
        return 0.5
    return round(d / (i + d), 3)
