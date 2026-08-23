#!/usr/bin/env python3
"""
PAINEL - monta o arquivo painel.html a partir dos dados coletados.
Voce nao precisa mexer neste arquivo.
"""

import csv
import html
import statistics
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).parent
PASTA = RAIZ / "dados"
SAIDA = RAIZ / "painel.html"
HOJE = date.today()

DIAS_PIN_NOVO = 45
MIN_DIAS = 3          # abaixo disso o painel avisa que ainda e cedo


# ---------------------------------------------------------------
# Carregar
# ---------------------------------------------------------------

def carregar(sufixo):
    linhas = []
    for arq in sorted(PASTA.glob(f"*-{sufixo}.csv")):
        with open(arq, encoding="utf-8") as f:
            linhas.extend(csv.DictReader(f))
    return linhas


def num(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def dias_entre(d1, d2):
    return (date.fromisoformat(d2) - date.fromisoformat(d1)).days


# ---------------------------------------------------------------
# Calcular
# ---------------------------------------------------------------

def calcular(pins):
    """Para cada pin: primeira e ultima vez visto -> saves por dia."""
    por_pin = defaultdict(list)
    for p in pins:
        por_pin[p["pin_id"]].append(p)

    resultado = []
    for pin_id, obs in por_pin.items():
        obs.sort(key=lambda x: x["data"])
        prim, ult = obs[0], obs[-1]
        dias = dias_entre(prim["data"], ult["data"])
        delta = num(ult["saves"]) - num(prim["saves"])
        idade = None
        if ult.get("criado_em"):
            try:
                idade = (HOJE - date.fromisoformat(ult["criado_em"])).days
            except ValueError:
                idade = None
        resultado.append({
            "pin_id": pin_id,
            "palavra": ult["palavra"],
            "titulo": ult["titulo"] or "(sem titulo)",
            "dominio": ult["dominio"],
            "link": ult["link"],
            "imagem": ult["imagem"],
            "video": ult["video"] == "1",
            "saves": num(ult["saves"]),
            "delta": delta,
            "dias": dias,
            "por_dia": round(delta / dias, 1) if dias > 0 else None,
            "idade": idade,
            "visto_em": ult["data"],
        })
    return resultado


def churn_por_palavra(pins):
    """Quanto do grid de busca troca de um dia para o outro, em %."""
    grade = defaultdict(lambda: defaultdict(set))
    for p in pins:
        grade[p["palavra"]][p["data"]].add(p["pin_id"])

    saida = {}
    for palavra, dias in grade.items():
        datas = sorted(dias)
        taxas = []
        for ant, atual in zip(datas, datas[1:]):
            hoje_set, ontem_set = dias[atual], dias[ant]
            if hoje_set:
                taxas.append(100.0 * len(hoje_set - ontem_set) / len(hoje_set))
        if taxas:
            saida[palavra] = round(statistics.mean(taxas), 1)
    return saida


def resumo_palavras(calc, pins, churn):
    por_palavra = defaultdict(list)
    for c in calc:
        por_palavra[c["palavra"]].append(c)

    saves_por_palavra = defaultdict(list)
    for p in pins:
        saves_por_palavra[p["palavra"]].append(num(p["saves"]))

    linhas = []
    for palavra, itens in por_palavra.items():
        vels = [i["por_dia"] for i in itens if i["por_dia"] is not None]
        saves = saves_por_palavra[palavra]
        linhas.append({
            "palavra": palavra,
            "velocidade": round(statistics.mean(vels), 1) if vels else None,
            "churn": churn.get(palavra),
            "saves_medio": int(statistics.median(saves)) if saves else 0,
            "topo": max(saves) if saves else 0,
            "pins": len(itens),
        })
    linhas.sort(key=lambda x: (x["velocidade"] is None, -(x["velocidade"] or 0)))
    return linhas


def resumo_dominios(calc):
    por_dom = defaultdict(list)
    for c in calc:
        if c["dominio"]:
            por_dom[c["dominio"]].append(c)
    linhas = []
    for dom, itens in por_dom.items():
        if len(itens) < 2:
            continue
        vels = [i["por_dia"] for i in itens if i["por_dia"] is not None]
        linhas.append({
            "dominio": dom,
            "pins": len(itens),
            "velocidade": round(statistics.mean(vels), 1) if vels else 0,
            "saves_medio": int(statistics.mean([i["saves"] for i in itens])),
            "tipo": classificar_dominio(dom),
        })
    linhas.sort(key=lambda x: -x["velocidade"])
    return linhas[:25]


def classificar_dominio(dom):
    d = dom.lower()
    if any(x in d for x in ("kiwify", "hotmart", "greenn", "eduzz", "monetizze", "braip")):
        return "INFOPRODUTO"
    if any(x in d for x in ("shopee", "amazon", "mercadolivre", "shein", "aliexpress", "magazineluiza", "americanas")):
        return "PRODUTO / AFILIADO"
    if any(x in d for x in ("etsy", "shopify", "nuvemshop", "lojaintegrada")):
        return "LOJA PROPRIA"
    if "pinterest" in d:
        return "SO PINTEREST"
    return "BLOG / CONTEUDO"


def sugestoes_novas(sug, janela=14):
    primeira = {}
    for s in sug:
        t = s["sugestao"]
        if t not in primeira or s["data"] < primeira[t]["data"]:
            primeira[t] = s
    novas = [s for s in primeira.values()
             if (HOJE - date.fromisoformat(s["data"])).days <= janela]
    novas.sort(key=lambda x: (x["data"], num(x["posicao"])), reverse=True)
    return novas[:40]


# ---------------------------------------------------------------
# HTML
# ---------------------------------------------------------------

def e(t):
    return html.escape(str(t if t is not None else ""))


def cartao_pin(p):
    idade = f'<span class="tag">{p["idade"]}d de idade</span>' if p["idade"] is not None else ""
    video = '<span class="tag video">VIDEO</span>' if p["video"] else ""
    vel = p["por_dia"] if p["por_dia"] is not None else "-"
    img = e(p["imagem"]) or ""
    destino = e(p["link"]) or f'https://www.pinterest.com/pin/{e(p["pin_id"])}/'
    return f"""
    <a class="pin" href="{destino}" target="_blank" rel="noopener">
      <div class="thumb"><img loading="lazy" src="{img}" alt=""></div>
      <div class="pin-corpo">
        <div class="vel">{vel} <small>saves/dia</small></div>
        <div class="titulo">{e(p["titulo"])[:90]}</div>
        <div class="meta">
          <span class="tag">{e(p["palavra"])}</span>
          {idade}{video}
        </div>
        <div class="rodape">{e(p["dominio"]) or "sem link"} &middot; {p["saves"]:,} saves</div>
      </div>
    </a>""".replace(",", ".")


def barra(valor, maximo, cor="var(--verde)"):
    if not maximo or valor is None:
        return ""
    pct = max(2, min(100, 100 * valor / maximo))
    return f'<div class="barra"><i style="width:{pct:.0f}%;background:{cor}"></i></div>'


def montar(pins, sug):
    datas = sorted({p["data"] for p in pins})
    dias_coletados = len(datas)
    calc = calcular(pins)
    churn = churn_por_palavra(pins)
    palavras = resumo_palavras(calc, pins, churn)
    dominios = resumo_dominios(calc)
    novas = sugestoes_novas(sug)

    acelerando = sorted(
        [c for c in calc if c["por_dia"] is not None and c["por_dia"] > 0],
        key=lambda x: -x["por_dia"])[:24]

    novos_pins = sorted(
        [c for c in calc if c["idade"] is not None and c["idade"] <= DIAS_PIN_NOVO
         and c["por_dia"] is not None and c["por_dia"] > 0],
        key=lambda x: -x["por_dia"])[:24]

    # avisos
    avisos = []
    if dias_coletados < MIN_DIAS:
        avisos.append(("cedo", f"Voce tem {dias_coletados} dia(s) de coleta. "
                               "Os numeros abaixo ainda nao significam nada. "
                               "Espere chegar a 14 dias antes de tomar decisao."))
    elif dias_coletados < 14:
        avisos.append(("cedo", f"{dias_coletados} dias de coleta. Ja da para olhar, "
                               "mas so confie de verdade a partir de 14."))
    if datas:
        atraso = (HOJE - date.fromisoformat(datas[-1])).days
        if atraso >= 2:
            avisos.append(("erro", f"A ultima coleta foi ha {atraso} dias. "
                                   "O robo parou. Quase sempre e o cookie que venceu - "
                                   "renove ele nos Secrets do GitHub."))

    max_vel = max([p["velocidade"] or 0 for p in palavras], default=1) or 1
    max_churn = max([p["churn"] or 0 for p in palavras], default=1) or 1

    linhas_palavras = "".join(f"""
      <tr>
        <td class="nome">{e(p["palavra"])}</td>
        <td class="n">{p["velocidade"] if p["velocidade"] is not None else "-"}
            {barra(p["velocidade"], max_vel)}</td>
        <td class="n">{str(p["churn"]) + "%" if p["churn"] is not None else "-"}
            {barra(p["churn"], max_churn, "var(--azul)")}</td>
        <td class="n">{p["saves_medio"]}</td>
        <td class="n dim">{p["pins"]}</td>
      </tr>""" for p in palavras)

    linhas_dom = "".join(f"""
      <tr>
        <td class="nome">{e(d["dominio"])}</td>
        <td><span class="pill p-{d["tipo"].split()[0].lower()}">{e(d["tipo"])}</span></td>
        <td class="n">{d["velocidade"]}</td>
        <td class="n dim">{d["pins"]}</td>
      </tr>""" for d in dominios)

    linhas_sug = "".join(f"""
      <tr>
        <td class="nome">{e(s["sugestao"])}</td>
        <td class="dim">{e(s["palavra_base"])}</td>
        <td class="n dim">{e(s["data"])}</td>
      </tr>""" for s in novas) or '<tr><td colspan="3" class="dim">Nenhuma palavra nova ainda.</td></tr>'

    html_avisos = "".join(
        f'<div class="aviso {tipo}">{e(txt)}</div>' for tipo, txt in avisos)

    grade_acel = "".join(cartao_pin(p) for p in acelerando) or '<p class="dim">Precisa de pelo menos 2 dias de coleta.</p>'
    grade_novos = "".join(cartao_pin(p) for p in novos_pins) or '<p class="dim">Nenhum pin recente acelerando ainda.</p>'

    return f"""<!doctype html>
<html lang="pt-BR"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Painel Pinterest</title>
<style>
:root{{--bg:#0d1117;--card:#161b22;--linha:#21262d;--txt:#e6edf3;--dim:#8b949e;
--verde:#3fb950;--azul:#58a6ff;--amarelo:#d29922;--vermelho:#f85149;}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--txt);
font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;padding:20px}}
.wrap{{max-width:1200px;margin:0 auto}}
h1{{font-size:22px;margin:0 0 4px}}
h2{{font-size:16px;margin:34px 0 6px;text-transform:uppercase;letter-spacing:.06em}}
.sub{{color:var(--dim);font-size:13px;margin:0 0 6px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin:18px 0}}
.kpi{{background:var(--card);border:1px solid var(--linha);border-radius:10px;padding:12px 14px}}
.kpi b{{display:block;font-size:24px;font-weight:600}}
.kpi span{{color:var(--dim);font-size:12px}}
.aviso{{border-radius:8px;padding:11px 14px;margin:10px 0;font-size:14px}}
.aviso.cedo{{background:rgba(210,153,34,.12);border:1px solid var(--amarelo);color:#f0c674}}
.aviso.erro{{background:rgba(248,81,73,.12);border:1px solid var(--vermelho);color:#ff9d96}}
table{{width:100%;border-collapse:collapse;background:var(--card);
border:1px solid var(--linha);border-radius:10px;overflow:hidden;font-size:14px}}
th{{text-align:left;padding:9px 12px;color:var(--dim);font-weight:500;font-size:11px;
text-transform:uppercase;letter-spacing:.06em;border-bottom:1px solid var(--linha)}}
td{{padding:9px 12px;border-bottom:1px solid var(--linha)}}
tr:last-child td{{border-bottom:none}}
.n{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
.dim{{color:var(--dim)}}
.nome{{font-weight:500}}
.barra{{height:3px;background:var(--linha);border-radius:2px;margin-top:4px;min-width:70px}}
.barra i{{display:block;height:100%;border-radius:2px}}
.pill{{font-size:10px;padding:2px 7px;border-radius:20px;border:1px solid var(--linha);
white-space:nowrap;letter-spacing:.03em}}
.p-infoproduto{{background:rgba(63,185,80,.15);color:var(--verde);border-color:var(--verde)}}
.p-produto{{background:rgba(88,166,255,.15);color:var(--azul);border-color:var(--azul)}}
.p-loja{{background:rgba(88,166,255,.1);color:var(--azul)}}
.grade{{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px;margin-top:10px}}
.pin{{background:var(--card);border:1px solid var(--linha);border-radius:10px;
overflow:hidden;text-decoration:none;color:inherit;display:block;transition:.15s}}
.pin:hover{{border-color:var(--azul);transform:translateY(-2px)}}
.thumb{{aspect-ratio:2/3;background:#000;overflow:hidden}}
.thumb img{{width:100%;height:100%;object-fit:cover;display:block}}
.pin-corpo{{padding:9px 10px}}
.vel{{font-size:19px;font-weight:600;color:var(--verde);line-height:1.1}}
.vel small{{font-size:10px;color:var(--dim);font-weight:400}}
.titulo{{font-size:12px;margin:5px 0;line-height:1.35;max-height:50px;overflow:hidden}}
.meta{{display:flex;flex-wrap:wrap;gap:4px;margin:6px 0}}
.tag{{font-size:9px;background:var(--linha);color:var(--dim);padding:2px 6px;border-radius:20px}}
.tag.video{{background:rgba(248,81,73,.2);color:#ff9d96}}
.rodape{{font-size:10px;color:var(--dim);border-top:1px solid var(--linha);padding-top:6px;
overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.legenda{{font-size:12px;color:var(--dim);margin-top:8px;line-height:1.6}}
</style></head><body><div class="wrap">

<h1>Painel Pinterest</h1>
<p class="sub">Atualizado em {HOJE.strftime('%d/%m/%Y')} &middot; dados de {e(datas[0]) if datas else '-'} ate {e(datas[-1]) if datas else '-'}</p>

{html_avisos}

<div class="kpis">
  <div class="kpi"><b>{dias_coletados}</b><span>dias de historico</span></div>
  <div class="kpi"><b>{len(calc):,}</b><span>pins acompanhados</span></div>
  <div class="kpi"><b>{len(palavras)}</b><span>nichos monitorados</span></div>
  <div class="kpi"><b>{len(novos_pins)}</b><span>pins novos subindo</span></div>
</div>

<h2>1. Onde vale a pena entrar</h2>
<p class="sub">Ordenado pelos nichos com audiencia mais ativa.</p>
<table>
<tr><th>Nicho</th><th class="n">Velocidade</th><th class="n">Renovacao</th>
<th class="n">Saves tipico</th><th class="n">Pins</th></tr>
{linhas_palavras}
</table>
<p class="legenda">
<b>Velocidade</b> = quantos saves por dia os pins desse nicho ganham. Alto = publico engajado.<br>
<b>Renovacao</b> = quanto da primeira pagina de busca troca por dia. Alto = o Pinterest esta
dando espaco para conteudo novo, da para entrar. Perto de zero = os mesmos pins antigos
travaram o topo e voce nao fura isso.<br>
<b>O melhor nicho tem os dois numeros altos.</b> Renovacao alta com velocidade baixa =
muita gente postando e ninguem salvando.
</p>

<h2>2. Pins novos que estao subindo</h2>
<p class="sub">Criados nos ultimos {DIAS_PIN_NOVO} dias e ja ganhando saves. Esta e a lista mais importante do painel.</p>
<div class="grade">{grade_novos}</div>
<p class="legenda">Abra uns 10 e procure o que se <b>repete</b>: mesmo enquadramento? texto
por cima da foto? titulo em pergunta ou em numero? Esse padrao e o modelo do seu proximo
criativo - de anuncio, de post e de capa de ebook.</p>

<h2>3. Pins com mais tracao no geral</h2>
<p class="sub">Inclui pins antigos. Serve para entender o que ja e consolidado no nicho.</p>
<div class="grade">{grade_acel}</div>

<h2>4. Quem ja ganha dinheiro nesses nichos</h2>
<table>
<tr><th>Site</th><th>Modelo</th><th class="n">Velocidade</th><th class="n">Pins</th></tr>
{linhas_dom}
</table>
<p class="legenda">Se aparecem muitos <b>infoprodutos</b>, o nicho compra ebook e curso.
Se sao <b>lojas e marketplaces</b>, e terreno de afiliado. Se e so <b>blog</b>,
a monetizacao ali e por anuncio e precisa de muito volume.</p>

<h2>5. Palavras novas que o Pinterest comecou a sugerir</h2>
<p class="sub">O autocomplete e alimentado por busca real. Termo novo ali = gente digitando aquilo agora.</p>
<table>
<tr><th>Palavra nova</th><th>Apareceu buscando</th><th class="n">Desde</th></tr>
{linhas_sug}
</table>

</div></body></html>"""


def main():
    if not PASTA.exists() or not list(PASTA.glob("*-pins.csv")):
        SAIDA.write_text(
            "<!doctype html><meta charset=utf-8>"
            "<body style='background:#0d1117;color:#e6edf3;font-family:sans-serif;padding:40px'>"
            "<h1>Ainda sem dados</h1><p>O robo ainda nao coletou nada. "
            "Volte amanha depois da primeira coleta.</p>", encoding="utf-8")
        print("Sem dados ainda - painel de espera gerado.")
        return

    pins = carregar("pins")
    sug = carregar("sugestoes")
    SAIDA.write_text(montar(pins, sug), encoding="utf-8")
    print(f"painel.html gerado: {len(pins)} linhas de pins, {len(sug)} de sugestoes.")


if __name__ == "__main__":
    main()
