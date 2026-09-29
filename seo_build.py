#!/usr/bin/env python3
"""
Portugal Radar — SEO (corre no GitHub Actions depois do radar_merge.py).

Uso:  python seo_build.py [<dir>]
Lê news.json + archive.json e escreve:
  - index.html: bloco estático com as últimas notícias entre <!--SEO:START--> e <!--SEO:END-->
    (o Google lê-o logo, sem precisar de correr o JavaScript; o JS substitui-o ao abrir)
  - páginas por secção: /politica/, /desporto/, /desporto/benfica/, /cor-de-rosa/famosos/ ...
  - sitemap.xml, feed.xml (RSS), robots.txt
Não mexe no news.json nem no radar_merge.py.
"""
import json, os, re, sys, html
from datetime import datetime, timezone
from email.utils import format_datetime
from zoneinfo import ZoneInfo

D = sys.argv[1] if len(sys.argv) > 1 else "."
P = lambda *n: os.path.join(D, *n)
SITE = "https://portugalradar.pt"
LX = ZoneInfo("Europe/Lisbon")
now = datetime.now(timezone.utc)
e = lambda s: html.escape(str(s or ""), quote=True)

# ---- secções (tem de bater certo com CATS do index.html e TOPICS/SUBS do radar_merge.py)
# topic -> (slug do URL, nome, título SEO, descrição)
SECS = {
    "politica": ("politica", "Política", "Política em Portugal — últimas notícias de hoje",
                 "Últimas notícias de política em Portugal: Governo, Parlamento, partidos e autárquicas, reunidas das principais fontes e atualizadas de hora a hora."),
    "desporto": ("desporto", "Desporto", "Desporto — últimas notícias de futebol e modalidades",
                 "Últimas notícias de desporto em Portugal: Benfica, Sporting, FC Porto, Seleção, Liga e modalidades, de A Bola, Record, O Jogo e outras fontes, hora a hora."),
    "economia": ("economia", "Economia & bolso", "Economia — últimas notícias que mexem com o seu bolso",
                 "Últimas notícias de economia em Portugal: preços, salários, impostos, habitação, bancos e empresas, explicadas de forma simples e atualizadas de hora a hora."),
    "saude": ("saude", "Saúde", "Saúde — últimas notícias do SNS e da saúde em Portugal",
              "Últimas notícias de saúde em Portugal: SNS, urgências, hospitais, médicos e estudos, reunidas das principais fontes e atualizadas de hora a hora."),
    "justica": ("justica", "Justiça & crime", "Justiça e crime — últimas notícias de Portugal",
                "Últimas notícias de justiça e crime em Portugal: tribunais, investigações, detenções e casos mediáticos, com a fonte original de cada notícia."),
    "rosa": ("cor-de-rosa", "Cor-de-rosa", "Cor-de-rosa — famosos, reality shows e realeza",
             "Últimas notícias cor-de-rosa: famosos portugueses, reality shows como a Casa dos Segredos, televisão e realeza, atualizadas de hora a hora."),
    "cultura": ("cultura", "Cultura & TV", "Cultura e TV — últimas notícias",
                "Últimas notícias de cultura e televisão em Portugal: cinema, música, livros, espetáculos e audiências, reunidas das principais fontes."),
    "tecnologia": ("tecnologia", "Tecnologia", "Tecnologia — últimas notícias",
                   "Últimas notícias de tecnologia em Portugal e no mundo: inteligência artificial, telemóveis, internet e startups portuguesas."),
    "tempo": ("tempo", "Tempo & alertas", "Tempo e alertas — avisos do IPMA, incêndios e proteção civil",
              "Previsão do tempo, avisos do IPMA, incêndios e alertas da Proteção Civil em Portugal, atualizados de hora a hora."),
    "mundo": ("mundo", "Mundo", "Mundo — últimas notícias internacionais",
              "As notícias internacionais que importam a Portugal: guerras, eleições, economia mundial e diplomacia, atualizadas de hora a hora."),
}
SUBS = {
    "desporto": [("benfica", "Benfica", "o Benfica"), ("sporting", "Sporting", "o Sporting"), ("porto", "FC Porto", "o FC Porto"),
                 ("braga", "Braga", "o SC Braga"), ("selecao", "Seleção", "a Seleção Nacional"), ("liga", "Liga e outros clubes", "a Liga Portugal"),
                 ("lafora", "Portugueses lá fora", "os portugueses a jogar no estrangeiro"), ("tenis", "Ténis", "o ténis"), ("golfe", "Golfe", "o golfe"),
                 ("ciclismo", "Ciclismo", "o ciclismo"), ("motores", "Motores", "a Fórmula 1, MotoGP e ralis"), ("basquetebol", "Basquetebol", "o basquetebol"),
                 ("andebol", "Andebol", "o andebol"), ("hoquei", "Hóquei", "o hóquei em patins"), ("futsal", "Futsal", "o futsal"),
                 ("voleibol", "Voleibol", "o voleibol"), ("atletismo", "Atletismo", "o atletismo"), ("triatlo", "Triatlo", "o triatlo"),
                 ("natacao", "Natação", "a natação"), ("surf", "Surf", "o surf"), ("rugby", "Râguebi", "o râguebi"), ("padel", "Padel", "o padel")],
    "rosa": [("reality", "Reality shows", "os reality shows (Casa dos Segredos, Big Brother e outros)"),
             ("famosos", "Famosos", "os famosos portugueses"), ("realeza", "Realeza", "as casas reais")],
}
ALWAYS_SUBS = {"benfica", "sporting", "porto", "braga", "selecao"}  # páginas sempre criadas (muito procuradas)
MIN_SUB_ITEMS = 3        # outras sub-secções só ganham página com pelo menos 3 notícias
PAGE_MAX = 40            # notícias por página de secção
HOME_PER_SEC = 4         # notícias por secção no bloco estático da capa

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def load(n, d):
    try:
        with open(P(n), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return d


def dt(ts):
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return now


def lx_label(ts):
    d = dt(ts).astimezone(LX)
    return f"{d.day} de {MESES[d.month-1]}, {d:%H:%M}"


news = load("news.json", {})
items = [i for i in news.get("items", []) if i.get("title") and i.get("url")]
ids = {i["id"] for i in items}
archive = [i for i in load("archive.json", {}).get("items", []) if i.get("id") not in ids and i.get("title") and i.get("url")]
items = sorted(items, key=lambda i: i.get("ts", ""), reverse=True)
pool = sorted(items + archive, key=lambda i: i.get("ts", ""), reverse=True)
updated = news.get("updated") or now.strftime("%Y-%m-%dT%H:%M:%SZ")
upd_lx = dt(updated).astimezone(LX)


def story(i, h="h3", img=True):
    src = e(i.get("source"))
    pic = ""
    if img and i.get("img"):
        pic = f'<img src="{e(i["img"])}" alt="" loading="lazy" decoding="async" width="120" height="80" referrerpolicy="no-referrer" onerror="this.remove()">'
    res = f'<p>{e(i.get("resumo"))}</p>' if i.get("resumo") else ""
    return (f'<article class="st">{pic}<{h}><a href="/#n/{e(i["id"])}">{e(i["title"])}</a></{h}>'
            f'<div class="mt"><time datetime="{e(i.get("ts"))}">{e(lx_label(i.get("ts")))}</time> · '
            f'<a href="{e(i["url"])}" rel="noopener" target="_blank">{src or "Fonte"}</a></div>{res}</article>')


# ---- páginas: topic/sub -> lista
pages = []  # (path, title, desc, h1, items, crumbs, jump_hash)
for t, (slug, name, title, desc) in SECS.items():
    lst = [i for i in pool if i.get("topic") == t]
    pages.append((f"/{slug}/", title, desc, name, lst[:PAGE_MAX], [(name, f"/{slug}/")], t))
    for s, sname, sfull in SUBS.get(t, []):
        sl = [i for i in lst if i.get("sub") == s]
        if s not in ALWAYS_SUBS and len(sl) < MIN_SUB_ITEMS:
            continue
        stitle = f"{sname} — últimas notícias de hoje"
        sdesc = (f"Últimas notícias sobre {sfull}, reunidas das principais fontes portuguesas, "
                 f"sem repetições e com a fonte original. Atualizado de hora a hora.")
        pages.append((f"/{slug}/{s}/", stitle, sdesc, sname, sl[:PAGE_MAX],
                      [(name, f"/{slug}/"), (sname, f"/{slug}/{s}/")], t))

NAV = "".join(f'<a href="/{s[0]}/">{e(s[1])}</a>' for s in SECS.values())
SUBNAV = {t: "".join(f'<a href="{p[0]}">{e(p[3])}</a>' for p in pages if p[6] == t and p[0].count("/") == 3) for t in SECS}

CSS = """:root{--paper:#f7f5f0;--ink:#17150f;--ink2:#5a564c;--rule:#cfc9bc;--red:#a8121f;--display:"Playfair Display",Georgia,serif;--body:"Source Serif 4",Georgia,serif;--ui:"IBM Plex Sans Condensed","Arial Narrow",system-ui,sans-serif}
@media (prefers-color-scheme:dark){:root{--paper:#15140f;--ink:#ece8dd;--ink2:#a39e90;--rule:#3a372d;--red:#e0475a}.logo{background:#f7f5f0;padding:6px 12px;border-radius:4px}}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.5 var(--body)}a{color:inherit}
.pg{max-width:880px;margin:0 auto;padding:0 16px 48px}.hd{text-align:center;padding:18px 0 10px;border-bottom:3px double var(--ink)}.logo{width:min(420px,80vw);height:auto}
nav.sec{display:flex;flex-wrap:wrap;gap:4px 14px;justify-content:center;padding:8px 0;border-bottom:1px solid var(--ink);font:600 12px var(--ui);letter-spacing:.08em;text-transform:uppercase}nav.sec a{text-decoration:none}nav.sec a:hover{color:var(--red)}
.bc{font:12px var(--ui);color:var(--ink2);margin:14px 0 0}.bc a{text-decoration:none}
h1{font:900 clamp(32px,6vw,52px)/1.05 var(--display);margin:6px 0 8px}.lede{color:var(--ink2);margin:0 0 10px}.upd{font:12px var(--ui);color:var(--ink2);text-transform:uppercase;letter-spacing:.06em}
.subs{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0}.subs a{font:600 12px var(--ui);border:1px solid var(--ink);padding:3px 9px;text-decoration:none}
.go{display:inline-block;margin:6px 0 14px;background:var(--red);color:#fff;font:600 13px var(--ui);padding:8px 14px;text-decoration:none;letter-spacing:.04em}
.st{border-top:1px solid var(--rule);padding:14px 0;overflow:hidden}.st img{float:right;width:120px;height:80px;object-fit:cover;margin:0 0 6px 14px;background:var(--rule)}
.st h2,.st h3{font:700 20px/1.25 var(--display);margin:0 0 4px}.st h2 a,.st h3 a{text-decoration:none}.st h2 a:hover,.st h3 a:hover{color:var(--red)}
.mt{font:12px var(--ui);color:var(--ink2);text-transform:uppercase;letter-spacing:.04em}.st p{margin:6px 0 0}
footer{margin-top:28px;padding-top:12px;border-top:3px double var(--ink);font:12px/1.6 var(--ui);color:var(--ink2)}footer nav a{margin-right:10px}"""

FONTS = '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=Source+Serif+4:opsz,wght@8..60,400&family=IBM+Plex+Sans+Condensed:wght@400;600&display=swap">'
GC = '<script data-goatcounter="https://portugalradar.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>'


def ld(obj):
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + "</script>"


def render_page(path, title, desc, h1, lst, crumbs, t):
    url = SITE + path
    full_title = f"{title} | Portugal Radar"
    bc = [{"@type": "ListItem", "position": 1, "name": "Portugal Radar", "item": SITE + "/"}] + \
         [{"@type": "ListItem", "position": n + 2, "name": c[0], "item": SITE + c[1]} for n, c in enumerate(crumbs)]
    data = [
        {"@context": "https://schema.org", "@type": "CollectionPage", "name": full_title, "description": desc, "url": url,
         "inLanguage": "pt-PT", "dateModified": updated, "isPartOf": {"@type": "WebSite", "name": "Portugal Radar", "url": SITE + "/"},
         "mainEntity": {"@type": "ItemList", "itemListElement": [
             {"@type": "ListItem", "position": n + 1, "url": i["url"], "name": i["title"]} for n, i in enumerate(lst[:20])]}},
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": bc},
    ]
    crumbs_html = '<a href="/">Início</a>' + "".join(f' › <a href="{c[1]}">{e(c[0])}</a>' for c in crumbs)
    subs = SUBNAV.get(t, "")
    body = "".join(story(i, "h2") for i in lst) or '<p class="lede">Sem notícias nesta secção nas últimas horas. Volte daqui a pouco.</p>'
    og = lst[0]["img"] if lst and lst[0].get("img") else SITE + "/og.jpg"
    return f"""<!doctype html>
<html lang="pt-PT"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(full_title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{url}">
<meta name="robots" content="index,follow,max-image-preview:large">
<meta property="og:type" content="website"><meta property="og:site_name" content="Portugal Radar"><meta property="og:locale" content="pt_PT">
<meta property="og:title" content="{e(full_title)}"><meta property="og:description" content="{e(desc)}"><meta property="og:url" content="{url}"><meta property="og:image" content="{e(og)}">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" type="image/png" href="/favicon.png"><link rel="apple-touch-icon" href="/apple-touch-icon.png"><link rel="manifest" href="/manifest.webmanifest">
<link rel="alternate" type="application/rss+xml" title="Portugal Radar" href="/feed.xml">
{FONTS}<style>{CSS}</style>
{ld(data)}
</head><body><div class="pg">
<header class="hd"><a href="/"><img class="logo" src="/logo.png" alt="Portugal Radar" width="1400" height="281"></a></header>
<nav class="sec" aria-label="Secções">{NAV}</nav>
<main>
<div class="bc">{crumbs_html}</div>
<h1>{e(h1)}: últimas notícias</h1>
<p class="lede">{e(desc)}</p>
<div class="upd">Atualizado a {upd_lx.day} de {MESES[upd_lx.month-1]} de {upd_lx.year}, {upd_lx:%H:%M} (hora de Lisboa)</div>
{f'<nav class="subs" aria-label="Sub-secções">{subs}</nav>' if subs else ''}
<a class="go" href="/#{e(t)}">Abrir {e(h1)} em direto no Portugal Radar →</a>
{body}
</main>
<footer><nav aria-label="Todas as secções"><a href="/">Capa</a>{NAV}</nav>
<p>Portugal Radar reúne as notícias de Portugal por tema, sem repetições e sempre com a fonte original. Cada resumo liga ao artigo completo no órgão de comunicação que o publicou. Contacto: <a href="mailto:contacto@portugalradar.pt">contacto@portugalradar.pt</a>.</p></footer>
</div>{GC}</body></html>
"""


written = []
for p in pages:
    out_dir = P(*p[0].strip("/").split("/"))
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_page(*p))
    written.append(p)

# ---- bloco estático na capa (index.html)
blk = [f'<div class="seo-static"><p class="upd">Edição de {upd_lx.day} de {MESES[upd_lx.month-1]} de {upd_lx.year}, {upd_lx:%H:%M}</p>']
for t, (slug, name, *_rest) in SECS.items():
    lst = [i for i in items if i.get("topic") == t][:HOME_PER_SEC]
    if not lst:
        continue
    blk.append(f'<section><h2><a href="/{slug}/">{e(name)}</a></h2>' + "".join(story(i, "h3", img=False) for i in lst) + "</section>")
blk.append("</div>")
home_block = "<!--SEO:START-->" + "".join(blk) + "<!--SEO:END-->"
foot_block = ("<!--SEOFOOT:START--><nav class=\"seo-nav\" aria-label=\"Secções\">"
              + "".join(f'<a href="{p[0]}">{e(p[3])}</a>' for p in written) + "</nav><!--SEOFOOT:END-->")

with open(P("index.html"), encoding="utf-8") as f:
    idx = f.read()
if "<!--SEO:START-->" in idx:
    idx = re.sub(r"<!--SEO:START-->.*?<!--SEO:END-->", lambda m: home_block, idx, flags=re.S)
if "<!--SEOFOOT:START-->" in idx:
    idx = re.sub(r"<!--SEOFOOT:START-->.*?<!--SEOFOOT:END-->", lambda m: foot_block, idx, flags=re.S)
with open(P("index.html"), "w", encoding="utf-8") as f:
    f.write(idx)

# ---- sitemap.xml
def lastmod(lst):
    return (lst[0].get("ts") if lst else None) or updated

urls = [(SITE + "/", updated, "hourly", "1.0")] + [(SITE + p[0], lastmod(p[4]), "hourly", "0.8" if p[0].count("/") == 2 else "0.6") for p in written]
sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
for u, lm, cf, pr in urls:
    sm.append(f"<url><loc>{u}</loc><lastmod>{lm}</lastmod><changefreq>{cf}</changefreq><priority>{pr}</priority></url>")
sm.append("</urlset>")
with open(P("sitemap.xml"), "w", encoding="utf-8") as f:
    f.write("\n".join(sm) + "\n")

# ---- feed.xml (RSS 2.0) — últimas 50
rss = ['<?xml version="1.0" encoding="UTF-8"?>',
       '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>',
       "<title>Portugal Radar</title>", f"<link>{SITE}/</link>",
       "<description>As notícias de Portugal que interessam, por tema, sem repetições e com a fonte. Atualizado de hora a hora.</description>",
       "<language>pt-PT</language>", f"<lastBuildDate>{format_datetime(dt(updated))}</lastBuildDate>",
       f'<atom:link href="{SITE}/feed.xml" rel="self" type="application/rss+xml"/>']
for i in items[:50]:
    cat = SECS.get(i.get("topic"), ("", "Outros"))[1]
    rss.append("<item>" + f"<title>{e(i['title'])}</title><link>{e(i['url'])}</link>"
               f'<guid isPermaLink="false">portugalradar-{e(i["id"])}</guid><pubDate>{format_datetime(dt(i.get("ts")))}</pubDate>'
               f"<category>{e(cat)}</category><description>{e((i.get('resumo') or '') + ' (' + (i.get('source') or '') + ')')}</description></item>")
rss.append("</channel></rss>")
with open(P("feed.xml"), "w", encoding="utf-8") as f:
    f.write("\n".join(rss) + "\n")

# ---- robots.txt
with open(P("robots.txt"), "w", encoding="utf-8") as f:
    f.write("User-agent: *\nAllow: /\nDisallow: /v2.html\nDisallow: /inbox/\n\n"
            f"Sitemap: {SITE}/sitemap.xml\n")

print(f"SEO: {len(written)} páginas de secção, {len(urls)} URLs no sitemap, {min(len(items), 50)} no RSS")
