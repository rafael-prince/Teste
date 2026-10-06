# Standalone prompt — MRE public agendas scraper

Paste the block below into a fresh Claude Code session. It is self-contained:
it carries the verified URLs, the verified HTML selectors, the measured
timings and the decisions already taken, so the new session does not repeat
the discovery work.

---

```
Download the Brazilian Foreign Ministry (MRE) public agendas from gov.br, one
HTML page per day, and convert them to CSV.

A working pipeline already exists. Do not rewrite it from scratch:

  repo:   https://github.com/rafael-prince/Teste
  branch: claude/mre-agendas-scraper-emn18z
  script: scripts/mre_agendas.py   (Python 3, standard library only)
  docs:   scripts/README-agendas-mre.md

Subcommands: probe | index | download | inspect | parse | zip | report

PREREQUISITE — network access
The cloud environment must allow egress to www.gov.br. Default "Trusted"
access does NOT include it and the proxy answers 403 to CONNECT. Fix it in
the environment selector (the cloud icon in the row above the message box at
claude.ai/code, NOT inside a running session): hover the environment, click
the gear, set Network access to Custom, add www.gov.br under Allowed domains,
and keep "Also include default list of common package managers" checked.
Existing sessions pick the change up within about a minute.

WHAT TO RUN
  python3 scripts/mre_agendas.py probe      # one page; expect HTTP 200
  python3 scripts/mre_agendas.py download   # resumable; ~6-8 hours
  python3 scripts/mre_agendas.py parse      # writes both CSVs
  python3 scripts/mre_agendas.py zip
  python3 scripts/mre_agendas.py report

The download is resumable: it skips any ./agendas_mre/<slug>/<date>.html that
already exists and is non-empty. Run it in the background in 2-hour windows
and chain them until it completes. Do not run authorities in parallel — keep
one request every 3 seconds in total.

VERIFIED AGENDA URLs (taken from the live index, not guessed)
  index   https://www.gov.br/mre/pt-br/acesso-a-informacao/agenda-de-autoridades/agendas-anteriores
  base    https://www.gov.br/mre/pt-br/agendas/agendas-de-autoridades-anteriores/

  Carlos Alberto Franco Franca    <base>agenda-antiga-carlos-alberto-franco-franca
  Ernesto Fraga Araujo            <base>agenda-antiga-ernesto-fraga-araujo
  Fernando Simas Magalhaes        <base>agenda-antiga-fernando-simas-magalhaes
  Otavio Brandelli                <base>agenda-antiga-otavio-brandelli
  Current minister                https://www.gov.br/mre/pt-br/agendas/agenda-do-ministro-das-relacoes-exteriores

Day pages are <agenda-url>/YYYY-MM-DD.
Date range: 2020-11-01 to 2022-12-31 for the four former authorities;
2023-01-01 to 2023-05-07 for the current minister. 3291 requests in total.

VERIFIED HTML STRUCTURE (gov.br Plone, portaltype-agendadiaria)
Confirmed on real pages from 2021, 2022 and 2023. The legacy agendas and the
current minister's agenda use the SAME template.

  ul.list-compromissos > li.item-compromisso-wrapper
      time.compromisso-inicio   "08h00"  -> hora_inicio  (normalise to 08:00)
      time.compromisso-fim      "08h30"  -> hora_fim
      h2.compromisso-titulo              -> descricao
      div.compromisso-local              -> local

  div.dados-agenda holds the day-level note, but also standing furniture that
  must be excluded or it will be mistaken for one: .brasao, .pessoa-area,
  .pessoa-nome, .pessoa-cargo, .calendar, .daypicker-wrapper,
  .search-compromisso.

OUTPUTS
  agendas_mre.csv         UTF-8, columns: autoridade, data, hora_inicio,
                          hora_fim, descricao, local, observacao_do_dia, url
  agendas_mre_filtro.csv  same columns, only rows whose descricao mentions:
                          Economia, Fazenda, Planejamento, Casa Civil, Guedes,
                          Ciro Nogueira, Braga Netto, Ramos, orcamento,
                          orcamentario.
                          Match on word boundaries over accent-stripped
                          lowercase text: bare substring "ramos" matches the
                          Portuguese verb forms declaramos / esperamos /
                          consideramos. "orcamento" and "orcamentario" should
                          also accept plurals and the feminine orcamentaria.

MEASURED TIMINGS (do not assume 3s per request)
  404, no agenda that day .... ~1.1 s
  200 with entries ........... 5.8 s / 8.2 s / 49.1 s observed
Socket timeout is set to 180 s because of that 49 s outlier. Total run is
roughly 6-8 hours, dominated by the days that actually have content; the
out-of-tenure 404s are the cheap ones, so trimming date ranges saves little.

KNOWN SITE BEHAVIOUR — read before changing request headers
www.gov.br sits behind an F5 Shape / BIG-IP ASM bot defense. A request with a
default curl User-Agent receives a TSPD/bobcmn JavaScript challenge page
containing the string "captcha"; a request with a browser User-Agent receives
the real page. The script sends a browser User-Agent, and the repository
owner has explicitly authorised proceeding on that basis.

Counter-evidence that this is permitted: https://www.gov.br/robots.txt says
"By default we allow robots to access all areas of our site already
accessible to anonymous users", excludes only Yandex from /mre, sets no
Crawl-delay, and its User-Agent: * rules cover query strings, Plone view
endpoints and asset files -- none of which match a clean agenda day path.

Stop immediately and report, without working around it, on the first HTTP 429
or challenge page the SCRIPT itself receives. A challenge page is non-empty,
so delete any you save or the resume logic will skip that date forever.

OPEN ITEM
observacao_do_dia is implemented but not positively verified: no sampled page
carried a day-level note. After the download, grep the corpus for non-empty
values and report whether the column ever fires.

REPORT AT THE END
Days requested, days with entries, empty days, 404s and errors, per authority
(`report` reads agendas_mre/_log.jsonl). Flag any layout_desconhecido events:
those are 200s that yielded no entries and carried none of the expected
containers, i.e. a template this parser does not know.
```
