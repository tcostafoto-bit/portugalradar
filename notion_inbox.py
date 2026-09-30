#!/usr/bin/env python3
"""Recolhe os lotes de notícias deixados pela tarefa agendada numa página do Notion
(sub-páginas da "caixa de entrada") e grava-os em inbox/*.json.

Uso:
  python3 notion_inbox.py pull     -> grava inbox/notion-<titulo>.json e a lista de ids em $NOTION_DONE
  python3 notion_inbox.py archive  -> arquiva no Notion as páginas listadas em $NOTION_DONE

Precisa de NOTION_TOKEN (secret do repositório) e NOTION_INBOX (id da página-mãe).
"""
import json, os, re, sys, urllib.request, urllib.error

TOKEN = os.environ.get("NOTION_TOKEN", "").strip()
INBOX = os.environ.get("NOTION_INBOX", "3eb1e872c5ae811a8946f719525a606e").replace("-", "")
DONE = os.environ.get("NOTION_DONE", "notion_done.txt")
API = "https://api.notion.com/v1"


def call(method, path, body=None):
    req = urllib.request.Request(
        API + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        msg = f"Notion {method} {path}: {e.code} {e.read()[:300].decode('utf-8', 'replace')}"
        print(f"::error::{msg}")
        raise SystemExit(msg)


def children(block_id):
    out, cursor = [], None
    while True:
        q = f"/blocks/{block_id}/children?page_size=100" + (f"&start_cursor={cursor}" if cursor else "")
        d = call("GET", q)
        out += d.get("results", [])
        if not d.get("has_more"):
            return out
        cursor = d.get("next_cursor")


def text_of(block):
    t = block.get("type")
    rt = (block.get(t) or {}).get("rich_text") or []
    return "".join(x.get("plain_text", "") for x in rt)


def extract_json(blocks):
    code = "".join(text_of(b) for b in blocks if b.get("type") == "code")
    raw = code if code.strip() else "\n".join(text_of(b) for b in blocks)
    raw = raw.strip()
    m = re.search(r"\{.*\}", raw, re.S)
    return json.loads(m.group(0) if m else raw)


def pull():
    if not TOKEN:
        print("NOTION_TOKEN em falta: nada a recolher")
        open(DONE, "w").close()
        return
    os.makedirs("inbox", exist_ok=True)
    pages = [b for b in children(INBOX) if b.get("type") == "child_page"]
    pages.sort(key=lambda b: b["child_page"].get("title", ""))
    done = []
    for p in pages:
        title = p["child_page"].get("title", "").strip()
        if title.upper().startswith("ERRO"):
            continue
        try:
            data = extract_json(children(p["id"]))
            if not isinstance(data, dict):
                raise ValueError("não é um objeto JSON")
        except Exception as e:  # JSON partido: marca a página e segue
            print(f"!! {title}: {e}")
            call("PATCH", f"/pages/{p['id']}", {"properties": {"title": {"title": [{"text": {"content": f"ERRO {title}"}}]}}})
            continue
        slug = re.sub(r"[^A-Za-z0-9_-]+", "-", title)[:60] or p["id"]
        path = f"inbox/notion-{slug}.json"
        json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False)
        done.append(p["id"])
        print(f"== {title} -> {path} ({len(data.get('new_items', []))} notícias)")
    open(DONE, "w").write("\n".join(done))
    print(f"Lotes recolhidos do Notion: {len(done)}")


def archive():
    if not TOKEN or not os.path.exists(DONE):
        return
    for pid in filter(None, open(DONE).read().split()):
        call("PATCH", f"/pages/{pid}", {"archived": True})
    print("Páginas do Notion arquivadas")


if __name__ == "__main__":
    {"pull": pull, "archive": archive}[sys.argv[1] if len(sys.argv) > 1 else "pull"]()
