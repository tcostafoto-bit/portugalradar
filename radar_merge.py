#!/usr/bin/env python3
"""
Portugal Radar — fusão de dados (corre em cada atualização).

Uso:  python radar_merge.py <dir>
  <dir>/news.json      estado atual (obrigatório; se faltar, começa vazio)
  <dir>/new_items.json lista de itens novos [{id,ts,source,lado,url,title,topic,sub,impacto,setores,tickers,resumo,img}]  (opcional)
  <dir>/market.json    {"contracts":{T:id}, "quotes":{T:{"price","pct"}}, "series":{T:[["ISO",close],...]}, "brief":[...], "fixes":[{"id":..,"tickers":[...]}]}  (opcional)
Escreve <dir>/news.json e <dir>/state.json e imprime uma linha de resumo.
"""
import json, os, re, sys, difflib
from datetime import datetime, timedelta, timezone

D = sys.argv[1] if len(sys.argv) > 1 else "."
P = lambda n: os.path.join(D, n)
now = datetime.now(timezone.utc)
KEEP_ITEMS_H, KEEP_SERIES_H, MAX_ITEMS, FUZZ = 120, 24 * 8, 300, 0.86
ARCHIVE_DAYS, ARCHIVE_MAX = 90, 3000  # arquivo: 90 dias, máx. 3000 notícias
# Temas e sub-temas do radar nacional. Muda aqui (e no CATS do index.html) para adaptar.
TOPICS = {"politica", "desporto", "rosa", "saude", "economia", "justica", "cultura", "tecnologia", "tempo", "mundo", "outros"}
SUBS = {
    "desporto": {"benfica", "sporting", "porto", "braga", "selecao", "liga", "lafora", "tenis", "golfe", "ciclismo", "motores", "basquetebol", "andebol", "hoquei", "futsal", "voleibol", "atletismo", "triatlo", "natacao", "surf", "rugby", "padel", "outros"},
    "rosa": {"reality", "famosos", "realeza", "outros"},
}
TOPICS_PT = TOPICS
LADOS = {"pt"}
IMP = {"alto", "medio", "baixo"}


def load(n, default):
    try:
        with open(P(n), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def iso(ts):
    """Normaliza qualquer data para ISO UTC 'YYYY-MM-DDTHH:MM:SSZ'; None se inválida."""
    if not ts:
        return None
    try:
        s = str(ts).strip().replace("Z", "+00:00")
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        try:
            from email.utils import parsedate_to_datetime
            d = parsedate_to_datetime(str(ts))
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return None


def norm_url(u):
    u = re.sub(r"[?#].*$", "", (u or "").strip())
    return u.rstrip("/").lower()


def norm_title(t):
    import unicodedata
    t = unicodedata.normalize("NFKD", (t or "").lower()).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    t = re.sub(r"\b(o|a|os|as|um|uma|de|da|do|das|dos|e|em|no|na|nos|nas|por|para|com|que|ao|aos|se|diz|afirma|garante|revela|the|of|to|in|on|and)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def img_url(u):
    """Só aceita imagens https simples (vindas do feed); caso contrário, vazio."""
    u = str(u or "").strip()
    if re.match(r"^https://[^\s\"'<>]{8,600}$", u):
        return u
    return ""


def clean_item(it):
    if not isinstance(it, dict):
        return None
    ts = iso(it.get("ts"))
    title = (it.get("title") or "").strip()
    url = (it.get("url") or "").strip()
    resumo = (it.get("resumo") or "").strip()
    if not (ts and title and url and resumo):
        return None
    tk = []
    for t in it.get("tickers") or []:
        if isinstance(t, dict) and t.get("t"):
            d = t.get("d") if t.get("d") in ("+", "-", "~") else "~"
            tk.append({"t": str(t["t"]).upper().strip(), "d": d})
        elif isinstance(t, str) and t.strip():
            tk.append({"t": t.upper().strip(), "d": "~"})
    lado = "pt"
    tset = TOPICS
    topic = it.get("topic") if it.get("topic") in tset else "outros"
    sub = str(it.get("sub") or "").lower().strip()
    if topic in SUBS:
        sub = sub if sub in SUBS[topic] else "outros"
    else:
        sub = ""
    return {
        "id": str(it.get("id") or re.sub(r"[^a-z0-9]+", "-", norm_url(url))[-60:]),
        "ts": ts,
        "source": str(it.get("source") or "—"),
        "lado": lado,
        "url": url,
        "title": title,
        "topic": topic,
        "sub": sub,
        "impacto": it.get("impacto") if it.get("impacto") in IMP else "baixo",
        "setores": [str(s) for s in (it.get("setores") or []) if str(s).strip()][:6],
        "tickers": tk[:7],
        "resumo": resumo,
        "img": img_url(it.get("img")),
    }


data = load("news.json", {})
items = [c for c in (clean_item(i) for i in data.get("items", [])) if c]
new_raw = load("new_items.json", [])
if isinstance(new_raw, dict):
    new_raw = new_raw.get("items", [])
market = load("market.json", {})

# ---- correções de direção em itens existentes (fixes)
fixed = 0
for fx in market.get("fixes") or []:
    for it in items:
        if it["id"] == fx.get("id") and fx.get("tickers"):
            c = clean_item({**it, "tickers": fx["tickers"]})
            if c:
                it["tickers"] = c["tickers"]
                fixed += 1

# ---- dedup + merge de itens novos
seen_url = {norm_url(i["url"]) for i in items}
seen_id = {i["id"] for i in items}
recent_titles = [norm_title(i["title"]) for i in items]
added, dup = 0, 0
for raw in new_raw:
    it = clean_item(raw)
    if not it:
        dup += 1
        continue
    nu, nt = norm_url(it["url"]), norm_title(it["title"])
    if nu in seen_url or it["id"] in seen_id:
        dup += 1
        continue
    if any(difflib.SequenceMatcher(None, nt, o).ratio() >= FUZZ for o in recent_titles if o):
        dup += 1
        continue
    # hora no futuro = fuso mal lido pelo feed (ex.: Lusa sem fuso, RTP adiantada 1h): recua hora a hora
    lim = (now + timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    k = 0
    while it["ts"] > lim and k < 3:
        it["ts"] = (datetime.strptime(it["ts"], "%Y-%m-%dT%H:%M:%SZ") - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        k += 1
    if it["ts"] > lim:
        it["ts"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    items.insert(0, it)
    seen_url.add(nu); seen_id.add(it["id"]); recent_titles.append(nt)
    added += 1

# ---- limpeza: 5 dias no feed, máx. 300; o resto vai para o arquivo (archive.json)
cut = (now - timedelta(hours=KEEP_ITEMS_H)).strftime("%Y-%m-%dT%H:%M:%SZ")
fut = (now + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
items = [i for i in items if i["ts"] <= fut]
items.sort(key=lambda i: i["ts"], reverse=True)
old_items = [i for i in items if i["ts"] < cut] + items[MAX_ITEMS:]
items = [i for i in items if i["ts"] >= cut][:MAX_ITEMS]
arch_raw = load("archive.json", [])
if isinstance(arch_raw, dict):
    arch_raw = arch_raw.get("items", [])
archive = [c for c in (clean_item(i) for i in arch_raw) if c]
aids = {i["id"] for i in archive} | {i["id"] for i in items}
moved = 0
for it in old_items:
    if it["id"] not in aids:
        archive.append(it); aids.add(it["id"]); moved += 1
acut = (now - timedelta(days=ARCHIVE_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
archive = sorted([i for i in archive if i["ts"] >= acut], key=lambda i: i["ts"], reverse=True)[:ARCHIVE_MAX]
with open(P("archive.json"), "w", encoding="utf-8") as f:
    json.dump({"updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "items": archive}, f, ensure_ascii=False, separators=(",", ":"))

# ---- mercado
contracts = dict(data.get("contracts") or {})
for k, v in (market.get("contracts") or {}).items():
    try:
        contracts[k.upper()] = int(v)
    except Exception:
        pass
quotes = dict(data.get("quotes") or {})
qn = 0
for k, v in (market.get("quotes") or {}).items():
    if isinstance(v, dict) and isinstance(v.get("price"), (int, float)):
        quotes[k.upper()] = {"price": float(v["price"]), "pct": float(v["pct"]) if isinstance(v.get("pct"), (int, float)) else None}
        qn += 1
series = {k: list(v) for k, v in (data.get("series") or {}).items()}
scut = (now - timedelta(hours=KEEP_SERIES_H)).strftime("%Y-%m-%dT%H:%M:%SZ")
sn = 0
for k, pts in (market.get("series") or {}).items():
    k = k.upper()
    cur = {p[0]: p[1] for p in series.get(k, []) if isinstance(p, list) and len(p) == 2}
    for p in pts or []:
        if isinstance(p, (list, tuple)) and len(p) == 2 and isinstance(p[1], (int, float)):
            t = iso(p[0])
            if t:
                cur[t] = float(p[1]); sn += 1
    series[k] = sorted([[t, c] for t, c in cur.items() if t >= scut])
for k in list(series):
    series[k] = [p for p in series[k] if p[0] >= scut]
    if not series[k]:
        del series[k]

# ---- frente a frente (pares de notícias que se contradizem ou respondem uma à outra)
ids = {i["id"] for i in items}
pairs = []
seen_pairs = set()
for pr in list(data.get("pairs") or []) + list(market.get("pairs") or []):
    if not isinstance(pr, dict):
        continue
    a, b = str(pr.get("a") or ""), str(pr.get("b") or "")
    key = tuple(sorted((a, b)))
    if a and b and a != b and a in ids and b in ids and key not in seen_pairs:
        seen_pairs.add(key)
        pairs.append({"a": a, "b": b, "tema": str(pr.get("tema") or "")[:120], "nota": str(pr.get("nota") or "")[:300]})
byid = {i["id"]: i for i in items}
pairs.sort(key=lambda p: max(byid[p["a"]]["ts"], byid[p["b"]]["ts"]), reverse=True)
pairs = pairs[:60]

# ---- versão e saída
ver = str(data.get("version") or "1.0.0").split(".")
try:
    ver = [int(x) for x in ver]
except Exception:
    ver = [1, 0, 0]
while len(ver) < 3:
    ver.append(0)
ver[2] += 1
version = ".".join(map(str, ver))
# brief: cada entrada é texto ("...") ou {"texto": "...", "id": "<id de um item>"}; o id só fica se o item existir
_ids = {it["id"] for it in items}
brief = []
for b in (market.get("brief") or data.get("brief") or []):
    if isinstance(b, dict):
        t = str(b.get("texto") or b.get("text") or "").strip()
        if not t:
            continue
        i = str(b.get("id") or "").strip()
        brief.append({"texto": t, "id": i} if i in _ids else {"texto": t})
    elif str(b).strip():
        brief.append({"texto": str(b).strip()})
brief = brief[:4]

out = {
    "version": version,
    "updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "brief": brief,
    "items": items,
    "contracts": contracts,
    "quotes": quotes,
    "quotesAt": market.get("quotesAt") or (now.strftime("%Y-%m-%dT%H:%M:%SZ") if qn else data.get("quotesAt")),
    "series": series,
    "pairs": pairs,
    "arquivo": len(archive),
}
with open(P("news.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

# estado compacto para a próxima corrida (o modelo só lê isto)
cut48 = (now - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
from collections import Counter
cnt = Counter(t["t"] for i in items for t in i["tickers"] if "." not in t["t"])
state = {
    "version": version,
    "updated": out["updated"],
    "recent": [{"id": i["id"], "ts": i["ts"], "topic": i["topic"], "sub": i.get("sub",""), "source": i["source"], "title": i["title"][:120]} for i in items if i["ts"] >= cut48][:120],
    "paired": sorted({x for p in pairs for x in (p["a"], p["b"])}),
    "top_tickers": [t for t, _ in cnt.most_common(12)],
    "contracts": {t: contracts[t] for t in contracts if t in cnt or t in quotes},
    "series_last": {t: (series[t][-1][0] if series.get(t) else None) for t in [t for t, _ in cnt.most_common(12)]},
}
with open(P("state.json"), "w", encoding="utf-8") as f:
    json.dump(state, f, ensure_ascii=False, indent=1)

print(f"v{version} · {len(pairs)} pares · +{added} novos · {moved} para o arquivo ({len(archive)} no arquivo) · {dup} descartados (repetidos/inválidos) · {fixed} direções corrigidas · {qn} cotações · {sn} pontos de histórico · {len(items)} itens")
