"""Desenho do Gantt para a tela e exportação SVG."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from xml.sax.saxutils import escape

from modelo import Evento, Tick, TipoEvento, chave_natural, cor_texto_sobre

T = TipoEvento


@dataclass
class Estilo:
    """Tamanhos usados no gráfico da tela e no SVG."""

    escala: float = 26.0
    altura_linha: int = 36
    altura_caixa: int = 16
    margem_esq: int = 92
    margem_dir: int = 30
    topo: int = 60
    altura_raia: int = 22
    fonte: int = 11
    mostrar_quantum: bool = True


@dataclass
class Prim:
    """Uma forma ou um texto que pode ser desenhado na tela e no SVG."""

    tipo: str
    pts: tuple = ()
    fill: Optional[str] = None
    stroke: Optional[str] = None
    largura: float = 1.0
    padrao: Optional[str] = None
    texto: str = ""
    ancora: str = "middle"
    tamanho: int = 10
    negrito: bool = False
    tracejado: bool = False
    dica: str = ""
    grupo: str = ""


@dataclass
class Desenho:
    """Tamanho do gráfico e lista de formas que serão desenhadas."""

    largura: int
    altura: int
    prims: List[Prim] = field(default_factory=list)


@dataclass
class Vista:
    """Dados da simulação necessários para montar o gráfico."""

    trace: List[Tick]
    eventos: List[Evento]
    cores: Dict[str, str]
    n_cpus: int
    t_fim: int
    titulo: str
    agora: Optional[int] = None


def vista_de(sim, com_agora: bool = False) -> Vista:
    """Separa os dados do gráfico até o ponto atual do histórico."""
    e = sim.estado
    trace, eventos = sim.trace_visivel(), sim.eventos_visiveis()
    n_cpus = max([len(t.cpus) for t in trace] + [len(e.cpus)])
    situacao = "finalizada" if sim.terminou else f"até t = {sim.relogio}"
    titulo = (f"Gráfico de Gantt — {e.algoritmo} · {n_cpus} CPU(s) · quantum {e.quantum} · "
              f"{situacao}")
    return Vista(trace, eventos, {t.id: t.cor for t in e.tarefas.values()}, n_cpus,
                 sim.relogio, titulo, sim.relogio if com_agora else None)


# Zona 'a': acima da tarefa, 'b': abaixo.
ICONES = {
    T.ATIVACAO:      ("b", "tri_cima",  "#1565C0", "ativação (entra na fila de prontos)"),
    T.TERMINO:       ("a", "tri_baixo", "#2E7D32", "término de ocorrência"),
    T.ENCERRAMENTO:  ("a", "quadrado",  "#000000", "tarefa encerrada"),
    T.PRAZO:         ("a", "tri_vazio", "#616161", "prazo cumprido"),
    T.PRAZO_PERDIDO: ("a", "xis",       "#D32F2F", "PRAZO PERDIDO"),
    T.PREEMPCAO:     ("b", "losango",   "#EF6C00", "preempção (perde a CPU)"),
    T.MIGRACAO:      ("b", "dupla",     "#7B1FA2", "migração para outra CPU"),
    T.SORTEIO:       ("b", "dado",      "#37474F", "sorteio de desempate"),
    T.SUSPENSAO:     ("b", "pausa",     "#000000", "suspensão"),
    T.RETOMADA:      ("b", "play",      "#000000", "retomada"),
    T.MODIFICACAO:   ("b", "estrela",   "#C2185B", "modificação manual"),
}
ORDEM_ICONES = list(ICONES)


def icone(nome: str, cx: float, cy: float, cor: str, s: float = 4.0, dica: str = "") -> List[Prim]:
    """Monta o símbolo de um evento em torno do ponto (cx, cy)."""
    P = Prim
    if nome == "tri_cima":
        return [P("poly", (cx, cy - s, cx - s, cy + s, cx + s, cy + s), fill=cor, dica=dica)]
    if nome == "tri_baixo":
        return [P("poly", (cx - s, cy - s, cx + s, cy - s, cx, cy + s), fill=cor, dica=dica)]
    if nome == "tri_vazio":
        return [P("poly", (cx - s, cy - s, cx + s, cy - s, cx, cy + s), fill="#FFFFFF",
                  stroke=cor, largura=1.2, dica=dica)]
    if nome == "quadrado":
        return [P("rect", (cx - s * .8, cy - s * .8, cx + s * .8, cy + s * .8), fill=cor, dica=dica)]
    if nome == "xis":
        return [P("line", (cx - s, cy - s, cx + s, cy + s), stroke=cor, largura=2.2, dica=dica),
                P("line", (cx - s, cy + s, cx + s, cy - s), stroke=cor, largura=2.2)]
    if nome == "losango":
        return [P("poly", (cx, cy - s, cx + s, cy, cx, cy + s, cx - s, cy), fill=cor, dica=dica)]
    if nome == "dupla":
        return [P("poly", (cx - s, cy - s, cx, cy, cx - s, cy + s), fill=cor, dica=dica),
                P("poly", (cx, cy - s, cx + s, cy, cx, cy + s), fill=cor)]
    if nome == "dado":
        return [P("rect", (cx - s, cy - s, cx + s, cy + s), fill="#FFFFFF", stroke=cor,
                  largura=1.2, dica=dica),
                P("circle", (cx - s * .5, cy - s * .5, 1.0), fill=cor),
                P("circle", (cx, cy, 1.0), fill=cor),
                P("circle", (cx + s * .5, cy + s * .5, 1.0), fill=cor)]
    if nome == "pausa":
        return [P("rect", (cx - s * .8, cy - s, cx - s * .2, cy + s), fill=cor, dica=dica),
                P("rect", (cx + s * .2, cy - s, cx + s * .8, cy + s), fill=cor)]
    if nome == "play":
        return [P("poly", (cx - s * .7, cy - s, cx - s * .7, cy + s, cx + s, cy), fill=cor, dica=dica)]
    if nome == "estrela":
        pts = []
        for k in range(8):
            r = s * 1.15 if k % 2 == 0 else s * .45
            a = math.pi / 4 * k - math.pi / 2
            pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
        return [P("poly", tuple(pts), fill=cor, dica=dica)]
    if nome == "circulo":
        return [P("circle", (cx, cy, s * .75), fill="#FFFFFF", stroke=cor, largura=1.2, dica=dica)]
    raise ValueError(nome)


def _trechos(chaves):
    """agrupa ticks iguais em intervalos [início, fim), ignorando None."""
    ini, atual = 0, None
    for t, k in enumerate(list(chaves) + [None]):
        if k != atual:
            if atual is not None:
                yield atual, ini, t
            ini, atual = t, k


def _passo_rotulo(escala: float) -> int:
    """Deixa espaço entre os números do eixo X para eles não se sobreporem."""
    for p in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 5000):
        if p * escala >= 30:
            return p
    return 10000


def construir(v: Vista, est: Optional[Estilo] = None) -> Desenho:
    """Monta o gráfico por tarefas, eventos e CPUs, com o menor ID perto do eixo X."""
    est = est or Estilo()
    P = Prim
    ids = sorted(v.cores, key=chave_natural)
    n = len(ids)
    T_ = max(v.t_fim, 1)
    x0 = est.margem_esq
    X = lambda t: x0 + t * est.escala

    # Reserva altura para os eventos que acontecem juntos.
    grupos: Dict[tuple, List[Evento]] = {}
    for ev in v.eventos:
        if ev.tipo in ICONES and ev.tarefa in v.cores:
            grupos.setdefault((ev.tarefa, ev.instante, ICONES[ev.tipo][0]), []).append(ev)
    faixa_eventos = max(1, max((len(g) for g in grupos.values()), default=1)) * 9 + 4
    altura_linha = max(est.altura_linha, est.altura_caixa + 2 * faixa_eventos)
    y_eixo = est.topo + n * altura_linha
    y_cpu0 = y_eixo + 30
    altura = y_cpu0 + v.n_cpus * (est.altura_raia + 4) + 10
    largura = int(x0 + T_ * est.escala + est.margem_dir)
    prims: List[Prim] = [P("rect", (0, 0, largura, altura), fill="#FFFFFF"),
                         P("text", (10, 20), texto=v.titulo, ancora="start", tamanho=est.fonte + 3,
                           negrito=True, grupo="rotulo")]

    # Eixo do tempo e linhas de referência.
    passo = _passo_rotulo(est.escala)
    for t in range(0, T_ + 1):
        if t % passo == 0:
            prims.append(P("line", (X(t), est.topo, X(t), altura - 8), stroke="#E3E3E3"))
            prims.append(P("text", (X(t), y_eixo + 15), texto=str(t), tamanho=est.fonte - 1))
        prims.append(P("line", (X(t), y_eixo, X(t), y_eixo + (6 if t % passo == 0 else 3)),
                       stroke="#000000"))
    prims.append(P("line", (x0, y_eixo, X(T_) + 6, y_eixo), stroke="#000000", largura=1.6))
    prims.append(P("text", (X(T_) + 8, y_eixo + 4), texto="t", ancora="start", tamanho=est.fonte,
                   negrito=True))

    # Posição e identificação das tarefas, com o menor ID embaixo.
    topo_caixa = (altura_linha - est.altura_caixa) // 2
    y_linha = {tid: est.topo + (n - 1 - i) * altura_linha for i, tid in enumerate(ids)}
    rotulos = [P("rect", (0, est.topo - 4, x0 - 6, altura), fill="#FFFFFF", grupo="rotulo")]
    for i, tid in enumerate(ids):
        yt = y_linha[tid]
        if i % 2 == 0:
            prims.append(P("rect", (x0, yt, X(T_), yt + altura_linha), fill="#F7F7F7"))
        rotulos.append(P("rect", (8, yt + altura_linha / 2 - 5, 18, yt + altura_linha / 2 + 5),
                         fill="#" + v.cores[tid], stroke="#000000", largura=.8, grupo="rotulo"))
        rotulos.append(P("text", (24, yt + altura_linha / 2 + 4), texto=tid, ancora="start",
                         tamanho=est.fonte + 1, negrito=True, grupo="rotulo"))

    # Junta ticks seguidos do mesmo estado em um único bloco.
    for tid in ids:
        yt = y_linha[tid] + topo_caixa
        yb = yt + est.altura_caixa
        estados = []
        for tk in v.trace:
            if tid in tk.cpus:
                estados.append(("exec", tk.cpus.index(tid) + 1))
            elif tid in tk.prontas:
                estados.append(("pronta", 0))
            elif tid in tk.suspensas:
                estados.append(("susp", 0))
            else:
                estados.append(None)
        for (tipo, cpu), a, b in _trechos(estados):
            xa, xb = X(a), X(b)
            if tipo == "exec":
                cor = "#" + v.cores[tid]
                prims.append(P("rect", (xa, yt, xb, yb), fill=cor, stroke="#000000", largura=.8,
                               dica=f"{tid} executando na CPU {cpu}: t={a} a t={b}"))
                rot = f"P{cpu}" if xb - xa >= 22 else (str(cpu) if xb - xa >= 9 else "")
                if rot:
                    prims.append(P("text", ((xa + xb) / 2, yt + est.altura_caixa / 2 + 3.5),
                                   texto=rot, tamanho=est.fonte - 2, negrito=True,
                                   fill=cor_texto_sobre(v.cores[tid])))
            elif tipo == "pronta":
                prims.append(P("rect", (xa, yt, xb, yb), stroke="#8A8A8A", largura=1.0,
                               dica=f"{tid} pronta (esperando CPU): t={a} a t={b}"))
            else:
                prims.append(P("rect", (xa, yt, xb, yb), fill="#FFFFFF", stroke="#000000",
                               largura=1.0, padrao="pontos",
                               dica=f"{tid} suspensa: t={a} a t={b}"))

    # Empilha eventos simultâneos sem deslocar seu instante no eixo X.
    for (tid, inst, zona), evs in grupos.items():
        evs.sort(key=lambda e: ORDEM_ICONES.index(e.tipo))
        yt = y_linha[tid]
        cy = yt + topo_caixa / 2 if zona == "a" else yt + topo_caixa + est.altura_caixa + topo_caixa / 2
        for k, ev in enumerate(evs):
            dy = (k - (len(evs) - 1) / 2) * 9
            _, nome, cor, _ = ICONES[ev.tipo]
            prims += icone(nome, X(ev.instante), cy + dy, cor, 3.6, dica=f"t={ev.instante}: {ev.texto}")
    for ev in v.eventos:
        if ev.tipo is T.MODIFICACAO and ev.tarefa not in y_linha:
            prims.append(P("line", (X(ev.instante), est.topo - 4, X(ev.instante), altura - 8),
                           stroke="#C2185B", tracejado=True, dica=f"t={ev.instante}: {ev.texto}"))
            prims += icone("estrela", X(ev.instante), est.topo - 8, "#C2185B", 3.6, ev.texto)

    # As linhas das CPUs também mostram os intervalos desligados.
    for c in range(v.n_cpus):
        yt = y_cpu0 + c * (est.altura_raia + 4)
        rotulos.append(P("text", (x0 - 10, yt + est.altura_raia / 2 + 4), texto=f"CPU {c + 1}",
                         ancora="end", tamanho=est.fonte, negrito=True, grupo="rotulo"))
        prims.append(P("rect", (x0, yt, X(T_), yt + est.altura_raia), stroke="#C8C8C8"))
        chaves = [(tk.cpus[c],) if c < len(tk.cpus) else None for tk in v.trace]
        for chave, a, b in _trechos(chaves):
            k = chave[0]
            xa, xb = X(a), X(b)
            if k is None:
                prims.append(P("rect", (xa, yt, xb, yt + est.altura_raia), fill="#EDEDED",
                               stroke="#9E9E9E", padrao="hachura",
                               dica=f"CPU {c + 1} DESLIGADA de t={a} a t={b} ({b - a} ticks)"))
                if xb - xa >= 58:
                    prims.append(P("text", ((xa + xb) / 2, yt + est.altura_raia / 2 + 4),
                                   texto="desligada", tamanho=est.fonte - 1, fill="#555555"))
            else:
                prims.append(P("rect", (xa, yt, xb, yt + est.altura_raia), fill="#" + v.cores[k],
                               stroke="#000000", largura=.8, dica=f"CPU {c + 1}: {k}, t={a} a t={b}"))
                if xb - xa >= 8 * len(k) + 4:
                    prims.append(P("text", ((xa + xb) / 2, yt + est.altura_raia / 2 + 4), texto=k,
                                   tamanho=est.fonte - 1, negrito=True, fill=cor_texto_sobre(v.cores[k])))
        if est.mostrar_quantum:
            for ev in v.eventos:
                if ev.tipo is T.QUANTUM and ev.cpu == c + 1:
                    prims += icone("circulo", X(ev.instante), yt + est.altura_raia, "#455A64", 3.2,
                                   f"t={ev.instante}: {ev.texto}")

    if v.agora is not None:
        prims.append(P("line", (X(v.agora), est.topo - 14, X(v.agora), altura - 8), stroke="#D50000",
                       largura=1.6, tracejado=True))
        prims.append(P("text", (X(v.agora), est.topo - 20), texto=f"t={v.agora}", tamanho=est.fonte,
                       negrito=True, fill="#D50000"))
    prims += rotulos
    return Desenho(largura, altura, prims)


def construir_legenda(largura: int, est: Optional[Estilo] = None, col: int = 250,
                      max_cols: int = 6) -> Desenho:
    """Monta a legenda de todos os elementos gráficos, em colunas."""
    est = est or Estilo()
    P = Prim
    itens = [("exec", "execução (P<n> = CPU usada)"),
             ("pronta", "pronta (espera CPU, sem cor)"),
             ("susp", "suspensa (preto pontilhado)"),
             ("off", "CPU desligada (sem tarefa)")]
    itens += [(("ic", t), ICONES[t][3]) for t in ORDEM_ICONES]
    itens += [("quantum", "quantum esgotado (escalonador)"),
              ("edicao", "modificação do sistema")]
    ncols = max(1, min(max_cols, (int(largura) - 20) // col))
    linhas = math.ceil(len(itens) / ncols)
    ancho = max(int(largura), col + 20)
    d = Desenho(ancho, 34 + linhas * 22,
                [P("rect", (0, 0, ancho, 34 + linhas * 22), fill="#FFFFFF"),
                 P("text", (10, 20), texto="Legenda", ancora="start", tamanho=est.fonte + 2,
                   negrito=True)])
    for i, (tipo, texto) in enumerate(itens):
        x = 10 + (i % ncols) * col
        y = 40 + (i // ncols) * 22
        if tipo == "exec":
            d.prims += [P("rect", (x, y - 8, x + 26, y + 8), fill="#4363D8", stroke="#000000", largura=.8),
                        P("text", (x + 13, y + 3.5), texto="P1", tamanho=est.fonte - 2, negrito=True,
                          fill="#FFFFFF")]
        elif tipo == "pronta":
            d.prims.append(P("rect", (x, y - 8, x + 26, y + 8), stroke="#8A8A8A"))
        elif tipo == "susp":
            d.prims.append(P("rect", (x, y - 8, x + 26, y + 8), fill="#FFFFFF", stroke="#000000",
                             padrao="pontos"))
        elif tipo == "off":
            d.prims.append(P("rect", (x, y - 8, x + 26, y + 8), fill="#EDEDED", stroke="#9E9E9E",
                             padrao="hachura"))
        elif tipo == "quantum":
            d.prims += icone("circulo", x + 13, y, "#455A64", 3.6)
        elif tipo == "edicao":
            d.prims.append(P("line", (x + 13, y - 9, x + 13, y + 9), stroke="#C2185B", tracejado=True))
            d.prims += icone("estrela", x + 13, y - 6, "#C2185B", 3.4)
        else:
            _, nome, cor, _ = ICONES[tipo[1]]
            d.prims += icone(nome, x + 13, y, cor, 4.2)
        d.prims.append(P("text", (x + 34, y + 4), texto=texto, ancora="start", tamanho=est.fonte))
    return d


def desenhar_tk(canvas, d: Desenho, tag: str = "gantt") -> None:
    """Desenha as formas no Canvas, incluindo os pontos e as hachuras."""
    ancoras = {"start": "sw", "middle": "s", "end": "se"}
    for p in d.prims:
        tags = (tag, p.grupo) if p.grupo else tag
        if p.tipo == "rect":
            x0, y0, x1, y1 = p.pts
            fundo = "#FFFFFF" if p.padrao == "pontos" else ("#EDEDED" if p.padrao == "hachura"
                                                           else (p.fill or ""))
            canvas.create_rectangle(x0, y0, x1, y1, fill=fundo, outline=p.stroke or "",
                                    width=p.largura, tags=tags)
            if p.padrao == "pontos":
                yy = y0 + 2.5
                while yy < y1 - 1:
                    xx = x0 + 2.5
                    while xx < x1 - 1:
                        canvas.create_oval(xx - 1.1, yy - 1.1, xx + 1.1, yy + 1.1, fill="#000000",
                                           outline="", tags=tags)
                        xx += 5
                    yy += 5
            elif p.padrao == "hachura":
                xx = x0 + 2.5
                while xx < x1 - 1:
                    canvas.create_line(xx, y0 + 1, xx, y1 - 1, fill="#9E9E9E", tags=tags)
                    xx += 5
        elif p.tipo == "line":
            canvas.create_line(*p.pts, fill=p.stroke or "#000000", width=p.largura,
                               dash=(4, 3) if p.tracejado else (), tags=tags)
        elif p.tipo == "poly":
            canvas.create_polygon(*p.pts, fill=p.fill or "", outline=p.stroke or "",
                                  width=p.largura, tags=tags)
        elif p.tipo == "circle":
            cx, cy, r = p.pts
            canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=p.fill or "",
                               outline=p.stroke or "", width=p.largura, tags=tags)
        elif p.tipo == "text":
            canvas.create_text(p.pts[0], p.pts[1], text=p.texto, anchor=ancoras[p.ancora],
                               fill=p.fill or "#000000", tags=tags,
                               font=("Helvetica", -p.tamanho, "bold" if p.negrito else "normal"))


def _num(x: float) -> str:
    """Formata os números do SVG sem casas decimais desnecessárias."""
    return f"{x:.1f}".rstrip("0").rstrip(".")


def para_svg(d: Desenho) -> str:
    """Gera o SVG a partir do desenho, sem tirar print da janela."""
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{d.largura}" height="{d.altura}" '
         f'viewBox="0 0 {d.largura} {d.altura}" font-family="DejaVu Sans, Arial, Helvetica, sans-serif">',
         '<defs>'
         '<pattern id="pontos" width="5" height="5" patternUnits="userSpaceOnUse">'
         '<rect width="5" height="5" fill="#FFFFFF"/><circle cx="2.5" cy="2.5" r="1.1" fill="#000000"/>'
         '</pattern>'
         '<pattern id="hachura" width="5" height="5" patternUnits="userSpaceOnUse">'
         '<rect width="5" height="5" fill="#EDEDED"/><line x1="2.5" y1="0" x2="2.5" y2="5" stroke="#9E9E9E"/>'
         '</pattern></defs>']
    for p in d.prims:
        fill = f"url(#{p.padrao})" if p.padrao else (p.fill or "none")
        stroke = p.stroke or "none"
        dica = f"<title>{escape(p.dica)}</title>" if p.dica else ""
        estilo = f'fill="{fill}" stroke="{stroke}" stroke-width="{_num(p.largura)}"'
        if p.tipo == "rect":
            x0, y0, x1, y1 = p.pts
            o.append(f'<rect x="{_num(x0)}" y="{_num(y0)}" width="{_num(x1 - x0)}" '
                     f'height="{_num(y1 - y0)}" {estilo}>{dica}</rect>')
        elif p.tipo == "line":
            x0, y0, x1, y1 = p.pts
            tr = ' stroke-dasharray="4 3"' if p.tracejado else ""
            o.append(f'<line x1="{_num(x0)}" y1="{_num(y0)}" x2="{_num(x1)}" y2="{_num(y1)}" '
                     f'stroke="{p.stroke or "#000000"}" stroke-width="{_num(p.largura)}"{tr}>{dica}</line>')
        elif p.tipo == "poly":
            pts = " ".join(f"{_num(p.pts[i])},{_num(p.pts[i + 1])}" for i in range(0, len(p.pts), 2))
            o.append(f'<polygon points="{pts}" {estilo}>{dica}</polygon>')
        elif p.tipo == "circle":
            cx, cy, r = p.pts
            o.append(f'<circle cx="{_num(cx)}" cy="{_num(cy)}" r="{_num(r)}" {estilo}>{dica}</circle>')
        elif p.tipo == "text":
            peso = ' font-weight="bold"' if p.negrito else ""
            o.append(f'<text x="{_num(p.pts[0])}" y="{_num(p.pts[1])}" text-anchor="{p.ancora}" '
                     f'font-size="{p.tamanho}"{peso} fill="{p.fill or "#000000"}">{escape(p.texto)}</text>')
    o.append("</svg>")
    return "\n".join(o)


def _deslocar(prims: List[Prim], dy: float) -> List[Prim]:
    """Move cópias das formas para colocar a legenda abaixo do gráfico."""
    import copy
    saida = []
    for p in prims:
        q = copy.copy(p)
        if p.tipo == "circle":
            q.pts = (p.pts[0], p.pts[1] + dy, p.pts[2])
        else:
            q.pts = tuple(c + (dy if i % 2 else 0) for i, c in enumerate(p.pts))
        saida.append(q)
    return saida


def estilo_para(t_fim: int) -> Estilo:
    """Ajusta a escala para caber mais tempo, preservando o gráfico completo."""
    return Estilo(escala=26.0 if t_fim <= 120 else 18.0 if t_fim <= 400 else 12.0)


def caminho_saida_padrao(origem: str, sufixo: str = "_gantt.svg") -> str:
    """Tenta salvar ao lado da configuração, depois tenta a pasta atual."""
    base = os.path.splitext(os.path.basename(origem or "simulacao"))[0] + sufixo
    pasta = os.path.dirname(os.path.abspath(origem)) if origem else os.getcwd()
    if not os.access(pasta, os.W_OK):
        pasta = os.getcwd()
    return os.path.join(pasta, base)


def exportar_svg(sim, caminho: str, est: Optional[Estilo] = None) -> str:
    """Exporta todo o histórico visível da simulação, incluindo a legenda."""
    v = vista_de(sim)
    principal = construir(v, est or estilo_para(v.t_fim))
    legenda = construir_legenda(principal.largura, est)
    largura = max(principal.largura, legenda.largura)
    prims = ([Prim("rect", (0, 0, largura, principal.altura + legenda.altura), fill="#FFFFFF")]
             + principal.prims + _deslocar(legenda.prims, principal.altura))
    svg = para_svg(Desenho(largura, principal.altura + legenda.altura, prims))
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(svg)
    return caminho
