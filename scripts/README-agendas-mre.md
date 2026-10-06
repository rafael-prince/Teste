# Agendas públicas do MRE — coletor e conversor

`mre_agendas.py` (Python 3, só biblioteca padrão).

## Estado

**A coleta não foi executada.** O contêiner desta sessão não tem acesso de
saída a `www.gov.br`: o proxy de egresso da organização respondeu **403 ao
CONNECT** para `www.gov.br:443`, antes de qualquer pacote chegar ao MRE.
Logo, *nada* se sabe ainda sobre o comportamento do servidor do MRE
(200 / 429 / CAPTCHA) — o teste do passo 1 não chegou a ser respondido por ele.

Os seletores de HTML em `parse_day()` são **provisórios**: foram validados
contra fixtures sintéticas (tabela e lista/`div`), não contra páginas reais.
Calibrar com `inspect` depois dos primeiros downloads.

## Ordem de execução

```sh
python3 scripts/mre_agendas.py probe        # passo 1: testa UMA página
python3 scripts/mre_agendas.py index        # passo 2: lista as URLs das autoridades
python3 scripts/mre_agendas.py download     # passos 3-4: um HTML por dia
python3 scripts/mre_agendas.py inspect agendas_mre/<slug>/<data>.html   # calibrar
python3 scripts/mre_agendas.py parse        # passos 5-6: os dois CSV
python3 scripts/mre_agendas.py zip          # passo 7
python3 scripts/mre_agendas.py report       # passo 7
```

## Garantias implementadas

- 3 s entre requisições (`DELAY_SECONDS`).
- Retomável: pula `agendas_mre/<slug>/<data>.html` já existente e não vazio.
- 404 e dia vazio: registrados em `agendas_mre/_log.jsonl` e segue adiante.
- **Parada imediata** no primeiro HTTP 429 ou página de bloqueio/CAPTCHA,
  informando autoridade e data; sem retentativa e sem contorno.
- `index` grava as URLs reais em `agendas_mre/_urls.json`, que passa a
  prevalecer sobre os slugs presumidos no código.

## Filtro (passo 6)

Os termos casam com **limite de palavra** sobre o texto normalizado
(minúsculas, sem acento). O limite não é cosmético: `ramos` como substring
solta casaria `declaramos`, `esperamos`, `consideramos`. `orcamento` e
`orcamentario` aceitam plural e o feminino `orçamentária`.

Volume previsto: 4 autoridades × 791 dias + 127 dias do ministro atual =
**3 291 requisições**, ~2 h 45 min a 3 s cada (sem contar erros).
