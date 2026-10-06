#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Revisa o relatorio .docx (e-Agendas 2023-2026) inserindo os encontros das
agendas gov.br (nov/2020-mai/2023) que sobreviveram a triagem
(agendas_mre_encontros.json). Edita word/document.xml in place, preservando
estilos, e acrescenta hyperlinks em word/_rels/document.xml.rels.

uso: mre_relatorio_docx.py <dir_descompactado> <saida.docx>
"""
import json, re, sys, os, shutil, zipfile, datetime as dt
from xml.sax.saxutils import escape
from collections import OrderedDict

UNP, OUT = sys.argv[1], sys.argv[2]
kept = json.load(open("agendas_mre_encontros.json", encoding="utf-8"))
DOC = os.path.join(UNP, "word", "document.xml")
RELS = os.path.join(UNP, "word", "_rels", "document.xml.rels")
x = open(DOC, encoding="utf-8").read()
rels = open(RELS, encoding="utf-8").read()

def esc(t): return escape(t, {'"': "&quot;"})

# ---------- fragmentos clonados do documento original ----------
tbl_i = x.find("<w:tbl>"); tbl_j = x.find("</w:tbl>") + len("</w:tbl>")
orig_tbl = x[tbl_i:tbl_j]
TBL_HEAD = orig_tbl[:orig_tbl.find("<w:tr")]                      # tblPr + tblGrid
HEADER_ROW = re.search(r"<w:tr\b.*?</w:tr>", orig_tbl, re.S).group(0)
FONT = '<w:rFonts w:ascii="Arial" w:cs="Arial" w:eastAsia="Arial" w:hAnsi="Arial"/>'
RPR17 = '<w:rPr>%s<w:sz w:val="17"/><w:szCs w:val="17"/></w:rPr>' % FONT
RPR17L = '<w:rPr>%s<w:color w:val="0563C1"/><w:sz w:val="17"/><w:szCs w:val="17"/><w:u w:val="single"/></w:rPr>' % FONT
BORD = ('<w:tcBorders><w:top w:val="single" w:color="A6A6A6" w:sz="4"/><w:left w:val="single" w:color="A6A6A6" w:sz="4"/>'
        '<w:bottom w:val="single" w:color="A6A6A6" w:sz="4"/><w:right w:val="single" w:color="A6A6A6" w:sz="4"/></w:tcBorders>')
MAR = '<w:tcMar><w:top w:type="dxa" w:w="60"/><w:left w:type="dxa" w:w="90"/><w:bottom w:type="dxa" w:w="60"/><w:right w:type="dxa" w:w="90"/></w:tcMar>'
WID = [1150, 1300, 3300, 3276]

def cell_p(text, rid=None):
    if rid:
        return ('<w:p><w:pPr><w:spacing w:after="40"/></w:pPr><w:hyperlink w:history="1" r:id="%s"><w:r>%s'
                '<w:t xml:space="preserve">%s</w:t></w:r></w:hyperlink></w:p>' % (rid, RPR17L, esc(text)))
    return '<w:p><w:pPr><w:spacing w:after="40"/></w:pPr><w:r>%s<w:t xml:space="preserve">%s</w:t></w:r></w:p>' % (RPR17, esc(text))

def cell(w, paras):
    return ('<w:tc><w:tcPr><w:tcW w:type="dxa" w:w="%d"/>%s%s<w:vAlign w:val="top"/></w:tcPr>%s</w:tc>'
            % (w, BORD, MAR, "".join(paras)))

def row(cells):
    return "<w:tr><w:trPr><w:cantSplit/></w:trPr>%s</w:tr>" % "".join(cells)

def table(rows_xml):
    return TBL_HEAD + HEADER_ROW + "".join(rows_xml) + "</w:tbl>"

def body_p(text):
    return ('<w:p><w:pPr><w:spacing w:after="160" w:line="300"/><w:jc w:val="both"/></w:pPr><w:r><w:rPr>%s'
            '<w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr><w:t xml:space="preserve">%s</w:t></w:r></w:p>' % (FONT, esc(text)))

def h1(text):
    return ('<w:p><w:pPr><w:pStyle w:val="Heading1"/><w:keepNext/><w:pageBreakBefore/><w:spacing w:after="160" w:before="320"/></w:pPr>'
            '<w:r><w:rPr>%s<w:b/><w:bCs/><w:color w:val="1F3864"/><w:sz w:val="26"/><w:szCs w:val="26"/></w:rPr>'
            '<w:t xml:space="preserve">%s</w:t></w:r></w:p>' % (FONT, esc(text)))

def h2(text):
    return ('<w:p><w:pPr><w:pStyle w:val="Heading2"/><w:keepNext/><w:spacing w:after="120" w:before="240"/></w:pPr>'
            '<w:r><w:rPr>%s<w:b/><w:bCs/><w:color w:val="1F3864"/><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr>'
            '<w:t xml:space="preserve">%s</w:t></w:r></w:p>' % (FONT, esc(text)))

def lai_p(text):
    return ('<w:p><w:pPr><w:spacing w:after="140" w:line="290"/><w:ind w:left="400" w:right="400"/><w:jc w:val="left"/></w:pPr>'
            '<w:r><w:rPr>%s<w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr><w:t xml:space="preserve">%s</w:t></w:r></w:p>' % (FONT, esc(text)))

def para_start(anchor_text):
    i = x.find(anchor_text); assert i > 0, anchor_text
    return x.rfind("<w:p>", 0, i)

def para_end(anchor_text):
    i = x.find(anchor_text); assert i > 0, anchor_text
    return x.find("</w:p>", i) + len("</w:p>")

# ---------- linhas das novas tabelas ----------
SHORT = {"Ernesto Fraga Araújo": "Ernesto Araújo", "Carlos Alberto Franco França": "Carlos França",
         "Mauro Vieira": "Mauro Vieira", "Otávio Brandelli": "Otávio Brandelli", "Fernando Simas Magalhães": "Fernando Simas Magalhães"}
new_rels = []
def mkrow(c, n):
    rid = "rIdgov%03d" % n
    new_rels.append('<Relationship Id="%s" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="%s" TargetMode="External"/>' % (rid, esc(c["url"])))
    d = dt.date.fromisoformat(c["data"]).strftime("%d/%m/%Y")
    hora = c["hora"].replace(":", "h")
    agenda = [cell_p(c["agenda"]), cell_p(SHORT[c["autoridade"]])]
    comp = [cell_p('"%s"' % c["titulo"])] + ([cell_p(c["local"])] if c["local"] else [])
    inter = c["orgao"] + "." + ((" " + c["observacao"]) if c["observacao"] else "")
    return row([cell(WID[0], [cell_p(d, rid), cell_p(hora)]), cell(WID[1], agenda), cell(WID[2], comp), cell(WID[3], [cell_p(inter)])])

bolso = [c for c in kept if c["data"] < "2023-01-01"]
lula = [c for c in kept if c["data"] >= "2023-01-01"]
rows_b = [mkrow(c, i) for i, c in enumerate(bolso, 1)]
rows_l = [mkrow(c, i) for i, c in enumerate(lula, len(bolso) + 1)]
n_ev = len({(c["data"], c["hora"]) for c in kept})
por_aut = OrderedDict()
for c in kept: por_aut[c["autoridade"]] = por_aut.get(c["autoridade"], 0) + 1

# ---------- 1) título e subtítulo ----------
x = x.replace("Encontros restritos do Ministro de Estado e da Secretária-Geral das Relações Exteriores com a Fazenda",
              "Encontros restritos do Ministro de Estado e da Secretaria-Geral das Relações Exteriores com a Fazenda", 1)
x = x.replace("Levantamento a partir do e-Agendas, 2023 a 2026. Dados extraídos em 5 de outubro de 2026.",
              "Levantamento a partir do e-Agendas (2023 a 2026) e das agendas publicadas em gov.br (novembro de 2020 a maio de 2023). Dados extraídos em 5 e 6 de outubro de 2026.", 1)

# ---------- 2) 1.5: frase sobre o intervalo coberto ----------
old = "A agenda do Ministro de Estado no e-Agendas só apresenta compromissos lançados manualmente a partir de 8 de maio de 2023."
assert old in x
x = x.replace(old, old + " O intervalo de 1º de janeiro a 7 de maio de 2023 foi coberto pela agenda publicada em gov.br (itens 1.6 e 3.2).", 1)

# ---------- 3) nova 1.6 antes do título "2. Encontros remanescentes" ----------
sec16 = h2("1.6 Extensão ao período anterior: agendas publicadas em gov.br") + body_p(
    "Para o período anterior ao registro do Ministro de Estado no e-Agendas, o levantamento foi estendido às agendas diárias "
    "publicadas no portal gov.br (seções \"Agendas de autoridades anteriores\" e \"Agenda do Ministro das Relações Exteriores\"). "
    "Foram coletadas, em 6 de outubro de 2026, as páginas de todos os dias de 1º de novembro de 2020 a 31 de dezembro de 2022 das agendas "
    "de Ernesto Fraga Araújo e Carlos Alberto Franco França, Ministros de Estado, e de Otávio Brandelli e Fernando Simas Magalhães, "
    "Secretários-Gerais, e de 1º de janeiro a 7 de maio de 2023 da agenda de Mauro Vieira: 3.291 dias requisitados, 1.181 com compromissos "
    "publicados e 4.614 compromissos no total.") + body_p(
    "A fonte difere do e-Agendas em três pontos. O registro em gov.br traz apenas título, horário e local, sem lista de participantes nem campo "
    "de assunto; por isso o critério de porte só pôde ser aplicado a posses e cerimônias, e os almoços foram mantidos, como na seção 2. "
    "Os órgãos foram mapeados para a estrutura vigente entre 2019 e 2022: o Ministério da Economia sucedeu à Fazenda e ao Planejamento, "
    "Desenvolvimento e Gestão, e abrange a Receita Federal e a Secretaria de Orçamento Federal. A Secretaria de Governo e a Secretaria-Geral "
    "da Presidência permanecem fora do escopo; as audiências do general Luiz Eduardo Ramos foram contadas apenas no intervalo em que chefiou "
    "a Casa Civil, de 29 de março a 3 de agosto de 2021.") + body_p(
    "A seleção por termos no título identificou 136 registros. Foram descartados 49 por homonímia ou termo fora de contexto (sobretudo "
    "\"Ramos\" e \"Planejamento Diplomático\"), 17 por envolverem órgão fora do escopo, 3 por se tratarem de posse ou cerimônia e 1 por tema "
    "de política externa. Restaram %d registros, correspondentes a %d eventos distintos, uma vez que seis compromissos do Ministro de Estado "
    "constam também da agenda do Secretário-Geral. Por autoridade: %s. A lista completa dos candidatos, com a classificação de cada um, "
    "consta da planilha agendas_mre_encontros.xlsx. Duas audiências com o Secretário Especial de Comércio Exterior e Assuntos Internacionais "
    "do Ministério da Economia foram mantidas por analogia à decisão do item 1.3, por constar o termo do cargo e não de tema declarado."
    % (len(kept), n_ev, "; ".join("%s, %d" % (SHORT[a], n) for a, n in por_aut.items())))
p = para_start("2. Encontros remanescentes")
x = x[:p] + sec16 + x[p:]
x = x.replace(">2. Encontros remanescentes<", ">2. Encontros remanescentes no e-Agendas (2023 a 2026)<", 1)

# ---------- 4) notas das duas linhas da SG confirmadas em gov.br ----------
old = "Compromisso do Ministro de Estado que não consta da agenda dele no e-Agendas."
assert x.count(old) == 2
x = x.replace(old, "Compromisso do Ministro de Estado que não consta da agenda dele no e-Agendas, mas consta da agenda do Ministro publicada em gov.br (item 3.2).")

# ---------- 5) nova seção 3 antes de "3. Sugestão" e renumeração ----------
sec3 = h1("3. Encontros anteriores a maio de 2023 nas agendas publicadas em gov.br") + body_p(
    "As tabelas a seguir trazem os registros das agendas publicadas em gov.br que sobreviveram à triagem descrita no item 1.6. Os títulos "
    "reproduzem o texto publicado, e cada data remete à página do dia em gov.br. Nenhum registro declara o assunto tratado. A sequência "
    "mais densa ocorre em junho de 2021, na agenda de Carlos França: Ministro-Chefe da Casa Civil em 8 e 10 de junho; Ministro da Economia "
    "em 9, 11 e 17 de junho; Secretário-Executivo da Casa Civil em 21 de junho; e Secretário-Executivo da Economia com o Secretário de "
    "Orçamento Federal em 22 de junho, os quatro últimos com a presença do Secretário-Geral.") \
    + h2("3.1 Novembro de 2020 a dezembro de 2022") + table(rows_b) \
    + body_p("") \
    + h2("3.2 Janeiro a maio de 2023, antes do registro do Ministro de Estado no e-Agendas") + table(rows_l) + body_p(
    "Os compromissos de 31 de março e 4 de abril de 2023 constam da seção 2 pela agenda da Secretária-Geral, com a observação de que não "
    "figuravam na agenda do Ministro de Estado no e-Agendas; a agenda publicada em gov.br confirma ambos na agenda do Ministro. O encontro "
    "de 26 de janeiro de 2023 com o Ministro-Chefe da Casa Civil não consta da agenda do Ministro de Estado no e-Agendas, que só se inicia "
    "em 8 de maio de 2023.")
p = para_start("3. Sugestão de pedido de acesso à informação")
x = x[:p] + sec3 + x[p:]
x = x.replace(">3. Sugestão de pedido de acesso à informação<", ">4. Sugestão de pedido de acesso à informação<", 1)

# ---------- 6) pedido LAI: introdução e datas do período anterior ----------
old_i = "O texto abaixo cobre os 16 eventos distintos e indaga sobre outros compromissos dedicados ao orçamento do Ministério."
assert old_i in x
x = x.replace(old_i, "O texto abaixo cobre os 16 eventos distintos da seção 2, relaciona em bloco separado as datas dos %d eventos da "
                     "seção 3 e indaga sobre outros compromissos dedicados ao orçamento do Ministério." % n_ev, 1)
def datas(cargo):
    return "; ".join(OrderedDict.fromkeys(dt.date.fromisoformat(c["data"]).strftime("%d/%m/%Y") for c in kept if c["cargo"] == cargo))
anchor = "Secretária-Geral: 18/01/2023; 31/03/2023; 04/04/2023; 23/08/2023; 16/08/2024; 27/11/2024; 27/03/2025."
assert anchor in x
e = para_end(anchor)
x = x[:e] + lai_p("Período anterior, conforme as agendas publicadas em gov.br — Ministro de Estado: %s." % datas("ME")) \
          + lai_p("Secretário-Geral: %s." % datas("SG")) + x[e:]

# ---------- 7) pontos a confirmar ----------
anchor = "o que permite cotejar as respostas."
e = para_end(anchor)
x = x[:e] + body_p(
    "A extensão ao período anterior a maio de 2023 (itens 1.6 e 3) baseia-se nas agendas publicadas em gov.br, e não no e-Agendas, e sua "
    "triagem dispôs apenas do título de cada compromisso. Convém decidir se o pedido deve abranger esse período; em caso afirmativo, "
    "ajustar o item 2, hoje limitado a 1º/01/2023, verificar a aplicabilidade temporal do Decreto nº 10.889/2021 aos registros de 2020 a "
    "2022 e conferir cada data na página correspondente de gov.br antes do envio.") + x[e:]

# ---------- gravar ----------
open(DOC, "w", encoding="utf-8").write(x)
rels = rels.replace("</Relationships>", "".join(new_rels) + "</Relationships>")
open(RELS, "w", encoding="utf-8").write(rels)
if os.path.exists(OUT): os.remove(OUT)
cwd = os.getcwd(); os.chdir(UNP)
with zipfile.ZipFile(os.path.join(cwd, OUT), "w", zipfile.ZIP_DEFLATED) as z:
    # [Content_Types].xml primeiro, por convencao
    z.write("[Content_Types].xml")
    for root, _d, files in os.walk("."):
        for f in files:
            fp = os.path.join(root, f)[2:]
            if fp != "[Content_Types].xml": z.write(fp)
os.chdir(cwd)
print("gravado %s | linhas 3.1: %d | linhas 3.2: %d | hyperlinks novos: %d" % (OUT, len(rows_b), len(rows_l), len(new_rels)))
