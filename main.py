"""Inicialização da interface e comandos de terminal."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import config
import gantt
from modelo import SEMENTE_PADRAO
from simulador import ErroEscalonador, Simulador

SAIDA_OK, SAIDA_USO, SAIDA_CONFIG, SAIDA_INCOMPLETA = 0, 1, 2, 3


def _imprimir_estatisticas(sim):
    """usa os mesmos totais apresentados pela interface gráfica."""
    print(f"{'Tarefa':<16}{'Ativações':>10}{'Concluídas':>11}{'Perdas':>9}{'Execução':>10}")
    for t in sim.estatisticas()['tarefas']:
        print(f"{t['id']:<16}{t['ativacoes']:>10}{t['concluidas']:>11}"
              f"{t['perdas']:>9}{t['exec']:>10}")
    for c in sim.estatisticas()['cpus']:
        print(f"CPU {c['indice']}: ocupada {c['ocupada']}, desligada {c['desligada']}, "
              f"uso {c['uso']:.1f}%")


def rodar_completo(args):
    """Executa até o fim pelo terminal e salva a imagem do Gantt."""
    cfg = config.carregar_arquivo(args.arquivo)
    for aviso in cfg.avisos:
        print('AVISO:', aviso)
    sim = Simulador(cfg, args.semente)
    motivo = sim.executar_ate_o_fim()
    if motivo != 'terminou':
        print('a simulação está esperando. Retome uma das tarefas suspensas.', file=sys.stderr)
        return SAIDA_INCOMPLETA
    print(f"Configuração: {cfg.algoritmo}, quantum {cfg.quantum}, {cfg.n_cpus} CPU(s)")
    _imprimir_estatisticas(sim)
    if args.eventos:
        for e in sim.eventos_visiveis():
            print(f't={e.instante}: {e.tipo.value}: {e.texto}')

    destino = args.saida or gantt.caminho_saida_padrao(args.arquivo)
    gantt.exportar_svg(sim, destino)
    print('Imagem do Gantt salva em:', os.path.abspath(destino))
    perdas = sum(t.perdas_prazo for t in sim.estado.tarefas.values())
    print(f'Simulação concluída em t = {sim.relogio}. Prazos perdidos: {perdas}.')
    return SAIDA_OK


def abrir_janela(args):
    """Carrega a interface só quando o programa precisa abrir uma janela."""
    from interface import Aplicacao
    Aplicacao(args.arquivo, semente=args.semente).executar()
    return SAIDA_OK


def autoteste(destino):
    """Verifica o núcleo, o histórico, o Tk e a exportação no pacote gerado."""
    import tkinter as tk
    from tkinter import ttk
    pasta = Path(destino).resolve()
    pasta.mkdir(parents=True, exist_ok=True)
    s = Simulador(config.carregar_texto(config.exemplo_padrao()))
    s.ir_para(6)
    antes = s.estado.clone()
    s.voltar()
    s.passo()
    assert s.estado == antes, 'Histórico inconsistente'
    assert s.executar_ate_o_fim() == 'terminou'
    assert all(t.concluidas == 10 for t in s.estado.tarefas.values())
    gantt.exportar_svg(s, str(pasta / 'autoteste.svg'))

    raiz = tk.Tk()
    raiz.withdraw()
    try:
        ttk.Label(raiz, text='Teste Tcl/Tk').pack()
        canvas = tk.Canvas(raiz)
        gantt.desenhar_tk(canvas, gantt.construir(gantt.vista_de(s)))
        raiz.update_idletasks()
        tk_version = str(raiz.tk.call('info', 'patchlevel'))
        tcl = str(raiz.tk.call('info', 'library'))
        tk_lib = str(raiz.tk.globalgetvar('tk_library'))
    finally:
        raiz.destroy()

    resultado = dict(ok=True, empacotado=bool(getattr(sys, 'frozen', False)),
                     executavel=sys.executable, python=sys.version,
                     tk=tk_version, tcl_library=tcl, tk_library=tk_lib,
                     bundle=getattr(sys, '_MEIPASS', None), ticks=s.relogio,
                     modulos={m: getattr(sys.modules[m], '__file__', '')
                              for m in ('config', 'modelo', 'simulador', 'gantt', 'tkinter')})
    if sys.platform == 'win32':
        import ctypes
        nome = ctypes.create_unicode_buffer(32768)
        ctypes.windll.kernel32.GetModuleFileNameW(ctypes.c_void_p(sys.dllhandle), nome, len(nome))
        resultado['python_dll'] = nome.value
    (pasta / 'autoteste.json').write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2), encoding='utf-8')
    print('autoteste passou. Resultados em:', pasta)
    return SAIDA_OK


def main(argv=None):
    """Lê os argumentos e escolhe entre abrir a janela e executar pelo terminal."""
    parser = argparse.ArgumentParser(description='Simulador de tarefas periódicas: RM e EDF.')
    parser.add_argument('arquivo', nargs='?', help='configuração de qualquer pasta')
    parser.add_argument('--completo', action='store_true', help='executar sem janela e exportar SVG')
    parser.add_argument('--saida', help='caminho do SVG no modo completo')
    parser.add_argument('--eventos', action='store_true', help='imprimir eventos no modo completo')
    parser.add_argument('--semente', type=int, default=SEMENTE_PADRAO,
                        help='semente para repetir os sorteios')
    parser.add_argument('--exemplo', action='store_true', help='imprimir uma configuração de exemplo')
    parser.add_argument('--autoteste', metavar='PASTA', help='verificar núcleo, Tcl/Tk e exportação')

    args = parser.parse_args(argv)
    if args.exemplo:
        print(config.exemplo_padrao(), end='')
        return SAIDA_OK
    if args.completo and not args.arquivo:
        print('Informe um arquivo de configuração com --completo.', file=sys.stderr)
        return SAIDA_USO

    try:
        if args.autoteste:
            return autoteste(args.autoteste)
        return rodar_completo(args) if args.completo else abrir_janela(args)
    except config.ErroConfig as exc:
        for aviso in exc.avisos:
            print('AVISO:', aviso, file=sys.stderr)
        print('ERRO no arquivo de configuração:', file=sys.stderr)
        for erro in exc.erros:
            print('- ' + erro, file=sys.stderr)
        return SAIDA_CONFIG
    except (OSError, ErroEscalonador) as exc:
        print(f'Não foi possível concluir: {exc}', file=sys.stderr)
        return SAIDA_INCOMPLETA
    except KeyboardInterrupt:
        print('execução interrompida.', file=sys.stderr)
        return SAIDA_INCOMPLETA


if __name__ == '__main__':
    # Evita falhas de impressão em terminais com codificação limitada.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(errors='replace')
    raise SystemExit(main())
