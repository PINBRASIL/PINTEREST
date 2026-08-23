#!/usr/bin/env python3
"""
COLETOR - roda sozinho no GitHub todo dia.
Voce nao precisa mexer neste arquivo.

O que ele faz: pergunta as mesmas palavras ao Pinterest todo dia
e salva o resultado num arquivo na pasta /dados.
"""

import csv
import json
import os
import random
import sys
import time
import unicodedata
import re
from datetime import datetime, date
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

COOKIE = os.environ.get("PINTEREST_COOKIE", "").strip()
APP_VERSION = os.environ.get("PINTEREST_APP_VERSION", "").strip() or "a1b2c3d"
PASTA = Path(__file__).parent / "dados"
HOJE = date.today().isoformat()

PAGINAS = 2
POR_PAGINA = 50
PAUSA_MIN, PAUSA_MAX = 4, 9

BASE = "https://www.pinterest.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

COLUNAS_PINS = ["data", "palavra", "pin_id", "posicao", "saves", "comentarios",
                "titulo", "dominio", "link", "imagem", "video", "criado_em"]
COLUNAS_SUG = ["data", "palavra_base", "sugestao", "posicao"]


def log(msg):
    print(f"  {msg}", flush=True)


# ---------------------------------------------------------------
# Conversa com o Pinterest
# ---------------------------------------------------------------

class Pinterest:
    def __init__(self):
        self.http = httpx.Client(
            timeout=30.0, follow_redirects=True,
            headers={
                "user-agent": UA,
                "accept": "application/json, text/javascript, */*, q=0.01",
                "accept-language": "pt-BR,pt;q=0.9",
                "referer": f"{BASE}/",
                "origin": BASE,
                "x-requested-with": "XMLHttpRequest",
                "x-app-version": APP_VERSION,
                "x-pinterest-appstate": "active",
                "screen-dpr": "2",
                "cookie": COOKIE,
            },
        )

    def _pedir(self, recurso, opcoes, url_origem, handler):
        r = self.http.get(
            f"{BASE}/resource/{recurso}/get/",
            params={
                "source_url": url_origem,
                "data": json.dumps({"options": opcoes, "context": {}}, separators=(",", ":")),
            },
            headers={"x-pinterest-source-url": url_origem, "x-pinterest-pws-handler": handler},
        )
        r.raise_for_status()
        return r.json()

    def buscar(self, palavra, marcador=None):
        opcoes = {"query": palavra, "scope": "pins", "page_size": POR_PAGINA,
                  "rs": "typed", "no_fetch_context_on_resource": False}
        if marcador:
            opcoes["bookmarks"] = [marcador]
        return self._pedir("BaseSearchResource", opcoes,
                           f"/search/pins/?q={quote(palavra)}&rs=typed",
                           "www/search/[scope].js")

    def sugestoes(self, palavra):
        return self._pedir("SearchTypeaheadResource",
                           {"query": palavra, "count": 12, "type": "pins"},
                           f"/search/pins/?q={quote(palavra)}",
                           "www/search/[scope].js")


# ---------------------------------------------------------------
# Leitura da resposta
# ---------------------------------------------------------------

def cavar(obj, *caminho, padrao=None):
    atual = obj
    for chave in caminho:
        if isinstance(atual, dict):
            atual = atual.get(chave)
        else:
            return padrao
        if atual is None:
            return padrao
    return atual


def pegar_itens(bruto):
    dados = cavar(bruto, "resource_response", "data")
    if isinstance(dados, list):
        return [x for x in dados if isinstance(x, dict)]
    if isinstance(dados, dict) and isinstance(dados.get("results"), list):
        return [x for x in dados["results"] if isinstance(x, dict)]
    return []


def pegar_marcador(bruto):
    m = cavar(bruto, "resource_response", "bookmark")
    return m if isinstance(m, str) and m not in ("-end-", "") else None


def data_criacao(valor):
    if not isinstance(valor, str):
        return ""
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(valor, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def ler_pin(item, posicao, palavra):
    pin_id = item.get("id")
    if not pin_id or item.get("type") not in (None, "pin"):
        return None

    imgs = item.get("images") or {}
    img = imgs.get("orig") or imgs.get("736x") or imgs.get("564x") or {}

    link = item.get("link") or ""
    dominio = ""
    if link:
        try:
            dominio = (urlparse(link).netloc or "").lower()
            if dominio.startswith("www."):
                dominio = dominio[4:]
        except ValueError:
            dominio = ""

    saves = cavar(item, "aggregated_pin_data", "aggregated_stats", "saves") \
        or item.get("repin_count") or 0
    coment = cavar(item, "aggregated_pin_data", "comment_count", padrao=item.get("comment_count") or 0)

    titulo = (item.get("grid_title") or item.get("title") or item.get("seo_title") or "").strip()
    titulo = re.sub(r"\s+", " ", titulo)[:200]

    return {
        "data": HOJE,
        "palavra": palavra,
        "pin_id": str(pin_id),
        "posicao": posicao,
        "saves": int(saves or 0),
        "comentarios": int(coment or 0),
        "titulo": titulo,
        "dominio": dominio,
        "link": link[:400],
        "imagem": img.get("url") or "",
        "video": "1" if (item.get("videos") or item.get("is_video")) else "0",
        "criado_em": data_criacao(item.get("created_at")),
    }


def ler_sugestoes(bruto, palavra_base):
    saida = []
    for i, item in enumerate(pegar_itens(bruto), start=1):
        termo = item.get("display_name") or item.get("query") or item.get("term")
        if isinstance(termo, str) and termo.strip():
            saida.append({"data": HOJE, "palavra_base": palavra_base,
                          "sugestao": termo.strip().lower(), "posicao": i})
    return saida


# ---------------------------------------------------------------
# Rotina
# ---------------------------------------------------------------

def carregar_palavras():
    arq = Path(__file__).parent / "palavras.txt"
    if not arq.exists():
        print("ERRO: arquivo palavras.txt nao encontrado.")
        sys.exit(1)
    palavras = []
    for linha in arq.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#"):
            palavras.append(linha.split("|")[0].strip().lower())
    return palavras


def main():
    if not COOKIE:
        print("ERRO: o cookie do Pinterest nao foi configurado.")
        print("Va em Settings > Secrets and variables > Actions e crie PINTEREST_COOKIE.")
        sys.exit(1)

    PASTA.mkdir(exist_ok=True)
    palavras = carregar_palavras()
    print(f"Coletando {len(palavras)} palavras em {HOJE}\n", flush=True)

    pin = Pinterest()
    todos_pins, todas_sug = [], []
    falhas = 0

    for i, palavra in enumerate(palavras, start=1):
        print(f"[{i}/{len(palavras)}] {palavra}", flush=True)
        achados = 0
        marcador = None

        for pagina in range(PAGINAS):
            try:
                bruto = pin.buscar(palavra, marcador)
            except Exception as e:
                log(f"falhou: {e}")
                falhas += 1
                break

            itens = pegar_itens(bruto)
            base = pagina * POR_PAGINA
            for j, item in enumerate(itens):
                p = ler_pin(item, base + j + 1, palavra)
                if p:
                    todos_pins.append(p)
                    achados += 1

            marcador = pegar_marcador(bruto)
            if not marcador or not itens:
                break
            time.sleep(random.uniform(PAUSA_MIN, PAUSA_MAX))

        try:
            sug = ler_sugestoes(pin.sugestoes(palavra), palavra)
            todas_sug.extend(sug)
        except Exception as e:
            log(f"sugestoes falharam: {e}")
            sug = []

        log(f"{achados} pins, {len(sug)} sugestoes")
        if i < len(palavras):
            time.sleep(random.uniform(PAUSA_MIN, PAUSA_MAX))

    # grava
    if todos_pins:
        with open(PASTA / f"{HOJE}-pins.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLUNAS_PINS)
            w.writeheader()
            w.writerows(todos_pins)
    if todas_sug:
        with open(PASTA / f"{HOJE}-sugestoes.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLUNAS_SUG)
            w.writeheader()
            w.writerows(todas_sug)

    print(f"\nTOTAL: {len(todos_pins)} pins, {len(todas_sug)} sugestoes, {falhas} falhas")

    if not todos_pins:
        print("\n*** NADA FOI COLETADO ***")
        print("Quase sempre significa que o cookie venceu. Renove nos Secrets.")
        sys.exit(1)


if __name__ == "__main__":
    main()
