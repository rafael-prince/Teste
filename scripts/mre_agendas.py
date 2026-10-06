#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coletor e conversor das agendas publicas de autoridades do MRE (gov.br).

Subcomandos
-----------
  probe      Testa UMA pagina e informa se o servidor responde 200, 429 ou
             devolve pagina de bloqueio / CAPTCHA.
  index      Baixa a pagina de "agendas anteriores" e lista as URLs de agenda
             das autoridades de interesse.
  download   Percorre todas as datas de cada autoridade salvando um HTML por
             dia em ./agendas_mre/<autoridade>/<data>.html
  inspect    Imprime a estrutura de um HTML ja salvo (para calibrar seletores).
  parse      Converte os HTML salvos em agendas_mre.csv e agendas_mre_filtro.csv
  zip        Compacta ./agendas_mre em agendas_mre_html.zip
  report     Resumo por autoridade: dias pedidos, dias com itens, erros.

Somente biblioteca padrao do Python 3.
"""

import argparse
import csv
import datetime as dt
import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from html.parser import HTMLParser

# --------------------------------------------------------------------------
# Configuracao
# --------------------------------------------------------------------------

BASE = "https://www.gov.br/mre/pt-br"
INDEX_URL = BASE + "/acesso-a-informacao/agenda-de-autoridades/agendas-anteriores"
MINISTRO_ATUAL_URL = BASE + "/agendas/agenda-do-ministro-das-relacoes-exteriores"

OUT_DIR = "agendas_mre"
LOG_PATH = os.path.join(OUT_DIR, "_log.jsonl")
CSV_FULL = "agendas_mre.csv"
CSV_FILTER = "agendas_mre_filtro.csv"

DELAY_SECONDS = 3.0
TIMEOUT_SECONDS = 180
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Autoridades pedidas. O slug e apenas um PALPITE inicial: o subcomando
# "index" sobrescreve esta tabela com as URLs realmente publicadas
# (gravadas em agendas_mre/_urls.json).
AUTORIDADES = [
    {
        "autoridade": "Carlos Alberto Franco Franca",
        "slug": "carlos-alberto-franco-franca",
        "url": BASE + "/agendas/agendas-de-autoridades-anteriores/"
                      "agenda-antiga-carlos-alberto-franco-franca",
        "inicio": "2020-11-01",
        "fim": "2022-12-31",
    },
    {
        "autoridade": "Ernesto Araujo",
        "slug": "ernesto-araujo",
        "url": None,
        "inicio": "2020-11-01",
        "fim": "2022-12-31",
    },
    {
        "autoridade": "Fernando Simas Magalhaes",
        "slug": "fernando-simas-magalhaes",
        "url": None,
        "inicio": "2020-11-01",
        "fim": "2022-12-31",
    },
    {
        "autoridade": "Otavio Brandelli",
        "slug": "otavio-brandelli",
        "url": None,
        "inicio": "2020-11-01",
        "fim": "2022-12-31",
    },
    {
        "autoridade": "Ministro das Relacoes Exteriores (atual)",
        "slug": "ministro-atual",
        "url": MINISTRO_ATUAL_URL,
        "inicio": "2023-01-01",
        "fim": "2023-05-07",
    },
]

# Palavras-chave do filtro (passo 6). Casadas com limite de palavra (\b) sobre
# o texto normalizado (minusculas, sem acento). O limite importa: "ramos" como
# substring solta casaria formas verbais comuns ("declaramos", "esperamos",
# "consideramos"); como palavra, casa o sobrenome. "orcamento" e
# "orcamentario" aceitam plural e o feminino "orcamentaria".
FILTRO_TERMOS = [
    r"\beconomia\b",
    r"\bfazenda\b",
    r"\bplanejamento\b",
    r"\bcasa civil\b",
    r"\bguedes\b",
    r"\bciro nogueira\b",
    r"\bbraga netto\b",
    r"\bramos\b",
    r"\borcamentos?\b",
    r"\borcamentari[oa]s?\b",
]
FILTRO_RE = [re.compile(t) for t in FILTRO_TERMOS]

# Marcadores de bloqueio / CAPTCHA.
BLOCK_MARKERS = [
    "acesso temporariamente interrompido",
    "acesso temporariamente bloqueado",
    "captcha",
    "g-recaptcha",
    "hcaptcha",
    "cf-challenge",
    "just a moment",
    "checking your browser",
    "attention required",
    "request unsuccessful",
    "too many requests",
]


class BlockedError(RuntimeError):
    """Servidor devolveu 429, CAPTCHA ou pagina de bloqueio."""


# --------------------------------------------------------------------------
# Utilitarios
# --------------------------------------------------------------------------

def strip_accents(s):
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def norm(s):
    """minusculas, sem acento, espacos colapsados."""
    return re.sub(r"\s+", " ", strip_accents(s or "").lower()).strip()


def daterange(start, end):
    d0 = dt.date.fromisoformat(start)
    d1 = dt.date.fromisoformat(end)
    cur = d0
    while cur <= d1:
        yield cur.isoformat()
        cur += dt.timedelta(days=1)


def log_event(**kw):
    kw["ts"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(kw, ensure_ascii=False) + "\n")


def looks_blocked(status, body):
    if status == 429:
        return "HTTP 429"
    low = norm(body[:20000])
    for m in BLOCK_MARKERS:
        if m in low:
            return "marcador: %r" % m
    # <title> explicito
    mt = re.search(r"<title[^>]*>(.*?)</title>", body[:20000], re.S | re.I)
    if mt and "acesso temporariamente" in norm(mt.group(1)):
        return "title: %s" % mt.group(1).strip()[:80]
    return None


def fetch(url):
    """Devolve (status, body). Levanta BlockedError em 429/CAPTCHA."""
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "pt-BR,pt;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            raw = resp.read()
            status = resp.getcode()
    except urllib.error.HTTPError as e:
        raw = e.read() or b""
        status = e.code
    except urllib.error.URLError as e:
        raise RuntimeError("falha de rede em %s: %s" % (url, e.reason))

    body = raw.decode("utf-8", errors="replace")
    reason = looks_blocked(status, body)
    if reason:
        raise BlockedError("%s em %s (%s)" % (
            "bloqueio" if status != 429 else "HTTP 429", url, reason))
    return status, body


# --------------------------------------------------------------------------
# Parsing de HTML
# --------------------------------------------------------------------------

class LinkParser(HTMLParser):
    """Coleta (href, texto) de todos os <a>."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self._href = None
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._buf = []

    def handle_data(self, data):
        if self._href is not None:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, re.sub(r"\s+", " ", "".join(self._buf)).strip()))
            self._href = None
            self._buf = []


class BlockParser(HTMLParser):
    """
    Lineariza o HTML em blocos de texto, preservando (a) a tag que abriu o
    bloco, (b) a classe, e (c) a profundidade. Serve tanto para extrair
    linhas de agenda quanto para o subcomando 'inspect'.
    """

    SKIP = {"script", "style", "noscript", "head"}
    BREAK = {"tr", "li", "p", "div", "br", "h1", "h2", "h3", "h4", "td", "th",
             "dt", "dd", "section", "article", "table", "tbody"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []          # [(tag, classe, texto)]
        self._stack = []
        self._cur = []
        self._cur_tag = "root"
        self._cur_cls = ""
        self._skip_depth = 0

    def _flush(self):
        txt = re.sub(r"[ \t\xa0]+", " ", "".join(self._cur))
        txt = re.sub(r"\s*\n\s*", "\n", txt).strip()
        if txt:
            self.blocks.append((self._cur_tag, self._cur_cls, txt))
        self._cur = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag in self.BREAK:
            self._flush()
            self._cur_tag = tag
            self._cur_cls = dict(attrs).get("class", "") or ""

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag in self.BREAK:
            self._flush()

    def handle_data(self, data):
        if self._skip_depth:
            return
        self._cur.append(data)

    def close(self):
        super().close()
        self._flush()


def main_content(body):
    """Recorta a regiao de conteudo da pagina Plone do gov.br, se possivel."""
    for pat in (
        r'<div[^>]+id="content-core".*?</div>\s*</div>',
        r'<div[^>]+id="content".*?(?=<footer|<div[^>]+id="portal-footer")',
        r'<main.*?</main>',
        r'<article.*?</article>',
    ):
        m = re.search(pat, body, re.S | re.I)
        if m:
            return m.group(0)
    return body


TIME_ANY = re.compile(r"\b([0-2]?\d)\s*[:hH]\s*([0-5]\d)\b")

# --------------------------------------------------------------------------
# Seletores reais do gov.br (Plone, portaltype-agendadiaria)
#
# Estrutura confirmada em paginas reais de 2021, 2022 e 2023 (agendas antigas
# e agenda do ministro atual usam o MESMO template):
#
#   <div class="dados-agenda">            <- nota do dia (quando houver)
#     <div class="brasao">...             <- descartar
#     <ul class="daypicker">...           <- faixa de dias; descartar
#   <ul class="list-compromissos">
#     <li class="item-compromisso-wrapper">
#       <time class="compromisso-inicio">08h00</time>
#       <time class="compromisso-fim">08h30</time>
#       <h2 class="compromisso-titulo">...</h2>
#       <div class="compromisso-local">...</div>
# --------------------------------------------------------------------------

ITEM_SPLIT = "item-compromisso-wrapper"
RE_INICIO = re.compile(r'<time[^>]*class="[^"]*compromisso-inicio[^"]*"[^>]*>(.*?)</time>', re.S | re.I)
RE_FIM = re.compile(r'<time[^>]*class="[^"]*compromisso-fim[^"]*"[^>]*>(.*?)</time>', re.S | re.I)
RE_TITULO = re.compile(r'<h\d[^>]*class="[^"]*compromisso-titulo[^"]*"[^>]*>(.*?)</h\d>', re.S | re.I)
RE_LOCAL = re.compile(r'<[^>]*class="[^"]*compromisso-local[^"]*"[^>]*>(.*?)</div>', re.S | re.I)
RE_TAGS = re.compile(r"<[^>]+>")
RE_DAYPICKER = re.compile(r'<ul[^>]*class="[^"]*daypicker[^"]*".*?</ul>', re.S | re.I)
RE_BRASAO = re.compile(r'<div[^>]*class="[^"]*brasao[^"]*".*?</div>', re.S | re.I)


def detag(s):
    return re.sub(r"\s+", " ", html.unescape(RE_TAGS.sub(" ", s or ""))).strip()


def to_hhmm(s):
    """'08h00' / '08:00' -> '08:00'."""
    m = re.search(r"([0-2]?\d)\s*[h:]\s*([0-5]\d)", detag(s), re.I)
    return "%02d:%02d" % (int(m.group(1)), int(m.group(2))) if m else ""


def layout_conhecido(body):
    """A pagina usa o template de agenda diaria esperado?"""
    return "list-compromissos" in body or "dados-agenda" in body


# Mobilia fixa do bloco .dados-agenda, repetida em todos os dias e que
# portanto NAO e observacao do dia.
NOTE_SKIP_CLASSES = (
    "brasao", "pessoa-area", "pessoa-nome", "pessoa-cargo", "calendar",
    "daypicker", "search-compromisso", "list-compromissos",
)
VOID_TAGS = {"br", "img", "input", "hr", "meta", "link", "source", "area"}


class NoteExtractor(HTMLParser):
    """Texto de .dados-agenda excluindo as subarvores de mobilia fixa."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._depth = 0
        self._skip_at = None

    def handle_starttag(self, tag, attrs):
        if tag in VOID_TAGS:
            return
        self._depth += 1
        if self._skip_at is None:
            cls = dict(attrs).get("class", "") or ""
            if any(c in cls for c in NOTE_SKIP_CLASSES):
                self._skip_at = self._depth

    def handle_startendtag(self, tag, attrs):
        return

    def handle_endtag(self, tag):
        if tag in VOID_TAGS:
            return
        if self._skip_at is not None and self._depth <= self._skip_at:
            self._skip_at = None
        self._depth -= 1

    def handle_data(self, data):
        if self._skip_at is None and data.strip():
            self.parts.append(data.strip())


def day_note(body):
    """Texto livre no topo do dia (cidade, fuso, aviso), se houver."""
    i = body.find("dados-agenda")
    if i < 0:
        return ""
    i = body.rfind("<", 0, i)              # recua ate o inicio da tag
    j = body.find("list-compromissos", i)
    if j > 0:
        j = body.rfind("<", i, j)          # corta ANTES da tag <ul ...>
        seg = body[i:j]
    else:
        seg = body[i:i + 30000]
    ne = NoteExtractor()
    ne.feed(seg)
    ne.close()
    return re.sub(r"\s+", " ", " ".join(ne.parts)).strip()[:500]


def parse_day(body, autoridade, data, url):
    """Extrai (linhas, observacao_do_dia) de um HTML de um dia."""
    obs = day_note(body)
    out = []
    for ch in body.split(ITEM_SPLIT)[1:]:
        ini = RE_INICIO.search(ch)
        fim = RE_FIM.search(ch)
        tit = RE_TITULO.search(ch)
        loc = RE_LOCAL.search(ch)
        descricao = detag(tit.group(1)) if tit else ""
        local = detag(loc.group(1)) if loc else ""
        hora_i = to_hhmm(ini.group(1)) if ini else ""
        hora_f = to_hhmm(fim.group(1)) if fim else ""
        if not (descricao or local or hora_i):
            continue
        out.append({
            "autoridade": autoridade,
            "data": data,
            "hora_inicio": hora_i,
            "hora_fim": hora_f,
            "descricao": descricao,
            "local": local,
            "observacao_do_dia": obs,
            "url": url,
        })
    return out, obs


# --------------------------------------------------------------------------
# Subcomandos
# --------------------------------------------------------------------------

def load_urls():
    path = os.path.join(OUT_DIR, "_urls.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            saved = json.load(fh)
        for a in AUTORIDADES:
            if a["slug"] in saved:
                a["url"] = saved[a["slug"]]
    return AUTORIDADES


def cmd_probe(args):
    url = args.url
    print("GET %s" % url)
    try:
        status, body = fetch(url)
    except BlockedError as e:
        print("BLOQUEADO: %s" % e)
        return 2
    except RuntimeError as e:
        print("ERRO DE REDE: %s" % e)
        return 3
    mt = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
    print("HTTP %s | %d bytes | title=%r" % (
        status, len(body), (mt.group(1).strip() if mt else "")[:120]))
    rows, obs = parse_day(body, "probe", "2022-04-20", url)
    print("itens reconhecidos: %d | observacao_do_dia=%r" % (len(rows), obs[:120]))
    for r in rows[:10]:
        print("  %s-%s | %s | %s" % (
            r["hora_inicio"], r["hora_fim"], r["descricao"][:90], r["local"][:40]))
    return 0 if status == 200 else 1


def cmd_index(args):
    status, body = fetch(INDEX_URL)
    print("HTTP %s em %s" % (status, INDEX_URL))
    lp = LinkParser()
    lp.feed(body)
    alvos = {
        "carlos-alberto-franco-franca": ["franco franca", "franca"],
        "ernesto-araujo": ["ernesto araujo", "araujo"],
        "fernando-simas-magalhaes": ["simas magalhaes", "magalhaes"],
        "otavio-brandelli": ["brandelli"],
    }
    achados = {}
    for href, text in lp.links:
        if not href:
            continue
        full = urllib.request.urljoin(INDEX_URL, href)
        hay = norm(text) + " " + norm(href)
        if "agenda" not in hay:
            continue
        for slug, keys in alvos.items():
            if any(k in hay for k in keys):
                achados.setdefault(slug, (full, text))
    print("\n--- URLs de agenda encontradas ---")
    for slug in alvos:
        if slug in achados:
            full, text = achados[slug]
            print("%-32s %s   [%s]" % (slug, full, text[:50]))
        else:
            print("%-32s NAO LISTADO" % slug)
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "_urls.json"), "w", encoding="utf-8") as fh:
        json.dump({k: v[0] for k, v in achados.items()}, fh,
                  ensure_ascii=False, indent=2)
    print("\ngravado em %s/_urls.json" % OUT_DIR)
    print("ministro atual (fixo): %s" % MINISTRO_ATUAL_URL)
    return 0


def cmd_download(args):
    autoridades = load_urls()
    if args.only:
        autoridades = [a for a in autoridades if a["slug"] in args.only]
    pendentes = [a for a in autoridades if not a["url"]]
    if pendentes:
        print("sem URL (rode 'index' primeiro): %s"
              % ", ".join(a["slug"] for a in pendentes))
        autoridades = [a for a in autoridades if a["url"]]

    total_new = 0
    for a in autoridades:
        destino = os.path.join(OUT_DIR, a["slug"])
        os.makedirs(destino, exist_ok=True)
        print("\n=== %s ===\n%s\n%s .. %s"
              % (a["autoridade"], a["url"], a["inicio"], a["fim"]))
        for data in daterange(a["inicio"], a["fim"]):
            path = os.path.join(destino, data + ".html")
            if os.path.exists(path) and os.path.getsize(path) > 0:
                continue  # retomada
            url = "%s/%s" % (a["url"].rstrip("/"), data)
            try:
                status, body = fetch(url)
            except BlockedError as e:
                print("\n*** PARADA: %s" % e)
                print("*** ultima autoridade: %s | ultima data: %s"
                      % (a["slug"], data))
                log_event(evento="bloqueio", slug=a["slug"], data=data,
                          url=url, detalhe=str(e))
                return 2
            except RuntimeError as e:
                print("  %s  erro de rede: %s" % (data, e))
                log_event(evento="erro_rede", slug=a["slug"], data=data,
                          url=url, detalhe=str(e))
                time.sleep(DELAY_SECONDS)
                continue

            if status == 404:
                log_event(evento="404", slug=a["slug"], data=data, url=url)
                print("  %s  404" % data)
            elif status != 200:
                log_event(evento="http_%d" % status, slug=a["slug"],
                          data=data, url=url)
                print("  %s  HTTP %s" % (data, status))
            else:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(body)
                total_new += 1
                rows, _ = parse_day(body, a["autoridade"], data, url)
                if not rows and not layout_conhecido(body):
                    log_event(evento="layout_desconhecido", slug=a["slug"],
                              data=data, url=url)
                    print("  %s  200 (LAYOUT DESCONHECIDO)" % data)
                elif not rows:
                    log_event(evento="vazio", slug=a["slug"], data=data, url=url)
                    print("  %s  200 (sem itens)" % data)
                else:
                    log_event(evento="ok", slug=a["slug"], data=data,
                              url=url, itens=len(rows))
                    print("  %s  200 (%d itens)" % (data, len(rows)))
            time.sleep(DELAY_SECONDS)
    print("\nnovos arquivos: %d" % total_new)
    return 0


def cmd_inspect(args):
    with open(args.path, encoding="utf-8", errors="replace") as fh:
        body = fh.read()
    print("=== %s (%d bytes) ===" % (args.path, len(body)))
    mt = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
    print("title: %r\n" % (mt.group(1).strip() if mt else ""))
    content = main_content(body)
    print("regiao de conteudo: %d bytes\n" % len(content))
    bp = BlockParser()
    bp.feed(content)
    bp.close()
    print("--- blocos (tag | classe | texto) ---")
    for tag, cls, txt in bp.blocks[:args.limit]:
        flag = "T" if TIME_ANY.search(txt) else " "
        print("[%s] %-6s %-28s %s" % (flag, tag, cls[:28], txt.replace("\n", " / ")[:140]))
    rows, obs = parse_day(body, "inspect", "0000-00-00", "")
    print("\n--- extraido: %d itens | obs=%r ---" % (len(rows), obs[:160]))
    for r in rows:
        print("  %s-%s | %s | local=%s"
              % (r["hora_inicio"], r["hora_fim"], r["descricao"][:100], r["local"][:40]))
    return 0


FIELDS = ["autoridade", "data", "hora_inicio", "hora_fim",
          "descricao", "local", "observacao_do_dia", "url"]


def cmd_parse(args):
    autoridades = {a["slug"]: a for a in load_urls()}
    all_rows = []
    for slug in sorted(os.listdir(OUT_DIR)):
        d = os.path.join(OUT_DIR, slug)
        if not os.path.isdir(d):
            continue
        meta = autoridades.get(slug, {"autoridade": slug, "url": ""})
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".html"):
                continue
            data = fn[:-5]
            path = os.path.join(d, fn)
            with open(path, encoding="utf-8", errors="replace") as fh:
                body = fh.read()
            url = "%s/%s" % ((meta.get("url") or "").rstrip("/"), data)
            rows, _ = parse_day(body, meta["autoridade"], data, url)
            all_rows.extend(rows)

    with open(CSV_FULL, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(all_rows)
    print("%s: %d linhas" % (CSV_FULL, len(all_rows)))

    filt = [r for r in all_rows
            if any(rx.search(norm(r["descricao"])) for rx in FILTRO_RE)]
    with open(CSV_FILTER, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(filt)
    print("%s: %d linhas" % (CSV_FILTER, len(filt)))
    return 0


def cmd_zip(args):
    import zipfile
    dest = args.dest
    n = 0
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(OUT_DIR):
            for fn in sorted(files):
                full = os.path.join(root, fn)
                z.write(full, os.path.relpath(full, "."))
                n += 1
    print("%s: %d arquivos, %.1f MiB"
          % (dest, n, os.path.getsize(dest) / 1048576.0))
    return 0


def cmd_report(args):
    stats = {}
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, encoding="utf-8") as fh:
            for line in fh:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                s = stats.setdefault(e.get("slug", "?"), {})
                s[e["evento"]] = s.get(e["evento"], 0) + 1
    print("%-32s %8s %8s %8s %8s %8s" % (
        "autoridade", "pedidos", "com_itens", "vazios", "404", "erros"))
    total = {}
    for slug, s in sorted(stats.items()):
        pedidos = sum(s.values())
        erros = sum(v for k, v in s.items()
                    if k.startswith("http_") or k in ("erro_rede", "bloqueio"))
        print("%-32s %8d %8d %8d %8d %8d" % (
            slug, pedidos, s.get("ok", 0), s.get("vazio", 0),
            s.get("404", 0), erros))
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("probe")
    sp.add_argument("url", nargs="?", default=(
        BASE + "/agendas/agendas-de-autoridades-anteriores/"
               "agenda-antiga-carlos-alberto-franco-franca/2022-04-20"))
    sp.set_defaults(func=cmd_probe)

    sp = sub.add_parser("index"); sp.set_defaults(func=cmd_index)

    sp = sub.add_parser("download")
    sp.add_argument("--only", nargs="*", default=None,
                    help="slugs a baixar (default: todos)")
    sp.set_defaults(func=cmd_download)

    sp = sub.add_parser("inspect")
    sp.add_argument("path")
    sp.add_argument("--limit", type=int, default=60)
    sp.set_defaults(func=cmd_inspect)

    sp = sub.add_parser("parse"); sp.set_defaults(func=cmd_parse)

    sp = sub.add_parser("zip")
    sp.add_argument("--dest", default="agendas_mre_html.zip")
    sp.set_defaults(func=cmd_zip)
    sp = sub.add_parser("report"); sp.set_defaults(func=cmd_report)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
