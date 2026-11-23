"""Leitura e validação dos arquivos de configuração."""

from __future__ import annotations

import os
import re
from typing import List, Optional

from escalonadores import nomes_disponiveis
from modelo import (CPUS_PADRAO, MAX_CPUS, QUANTUM_PADRAO, ConfigSistema, TCB,
                    cor_padrao)

REGEX_COR = re.compile(r"^#?([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})$")
REGEX_SERVIDOR = re.compile(r"^(BS|PS|DS|SS)\d+$", re.IGNORECASE)


class ErroConfig(Exception):
    """Erros encontrados na leitura da configuração."""

    def __init__(self, erros: List[str], avisos: Optional[List[str]] = None):
        """Guarda os erros e avisos para mostrar tudo de uma vez."""
        self.erros = list(erros)
        self.avisos = list(avisos or [])
        super().__init__("\n".join(self.erros))


def ler_texto(caminho: str) -> str:
    """tenta UTF-8 primeiro, depois as codificações antigas do Windows."""
    if not caminho or not os.path.exists(caminho):
        raise ErroConfig([f"Arquivo não encontrado: '{caminho}'."])
    if os.path.isdir(caminho):
        raise ErroConfig([f"'{caminho}' é uma pasta, não um arquivo de configuração"])
    try:
        with open(caminho, "rb") as f:
            dados = f.read()
    except OSError as exc:
        raise ErroConfig([f"Não foi possível abrir '{caminho}': {exc.strerror or exc}."])
    for codificacao in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return dados.decode(codificacao)
        except UnicodeDecodeError:
            continue
    raise ErroConfig([f"Não foi possível decodificar o texto de '{caminho}'"])


def carregar_arquivo(caminho: str) -> ConfigSistema:
    """Lê o arquivo e confere a configuração."""
    cfg = carregar_texto(ler_texto(caminho), origem=caminho)
    return cfg


def _campos(linha: str) -> List[str]:
    """Separa os campos e remove espaços e separadores vazios no final."""
    campos = [c.strip() for c in linha.split(";")]
    while campos and campos[-1] == "":
        campos.pop()
    return campos


def _inteiro(texto: str, nome: str, n: int, erros: List[str], minimo: int) -> Optional[int]:
    """Confere o número e o mínimo permitido, guardando o erro se houver."""
    try:
        valor = int(texto)
    except ValueError:
        erros.append(f"Linha {n}: o campo '{nome}' deve ser um número inteiro "
                     f"(valor recebido: '{texto}').")
        return None
    if valor < minimo:
        erros.append(f"Linha {n}: o campo '{nome}' deve ser maior ou igual a {minimo} "
                     f"(valor recebido: {valor}).")
        return None
    return valor


def carregar_texto(texto: str, origem: str = "") -> ConfigSistema:
    """Lê a configuração e junta os erros antes de avisar."""
    erros: List[str] = []
    avisos: List[str] = []
    cfg = ConfigSistema(origem=origem)
    linhas = [(n, bruta.strip()) for n, bruta in enumerate(texto.splitlines(), start=1)]
    linhas = [(n, l) for n, l in linhas if l and not l.startswith("#")]
    if not linhas:
        raise ErroConfig(["O arquivo está vazio: faltam a linha de parâmetros do sistema e "
                          "ao menos uma tarefa."])

    # A primeira linha configura o sistema. As demais descrevem as tarefas.
    n, linha = linhas[0]
    c = _campos(linha)
    disponiveis = nomes_disponiveis()
    algoritmo = c[0].upper() if c else ""
    if algoritmo not in disponiveis:
        erros.append(f"Linha {n}: algoritmo de escalonamento '{c[0] if c else ''}' "
                     f"desconhecido. Disponíveis: {', '.join(disponiveis)}.")
    cfg.algoritmo = algoritmo
    if len(c) >= 2:
        q = _inteiro(c[1], "quantum", n, erros, 0)
        cfg.quantum = QUANTUM_PADRAO if q is None else q
    else:
        avisos.append(f"Linha {n}: quantum ausente, usando o padrão {QUANTUM_PADRAO}.")
    if len(c) >= 3:
        m = _inteiro(c[2], "qtde_cpus", n, erros, 1)
        if m is not None and m > MAX_CPUS:
            erros.append(f"Linha {n}: qtde_cpus={m} passa do limite de CPUs do simulador "
                         f"({MAX_CPUS}).")
            m = None
        cfg.n_cpus = CPUS_PADRAO if m is None else m
    else:
        avisos.append(f"Linha {n}: qtde_cpus ausente, usando o padrão {CPUS_PADRAO}.")
    if len(c) > 3:
        avisos.append(f"Linha {n}: campos além de qtde_cpus foram ignorados.")

    ids_vistos = {}
    cores_vistas = {}
    n_com_eventos = 0
    for n, linha in linhas[1:]:
        c = _campos(linha)
        c += [""] * (6 - len(c))
        id_, cor, ing, dur, per, pzo = c[:6]
        eventos = tuple(e for e in c[6:] if e)
        n_erros_antes = len(erros)
        if not id_:
            erros.append(f"Linha {n}: o campo 'id' é obrigatório.")
        elif id_.lower() in ids_vistos:
            erros.append(f"Linha {n}: id '{id_}' repetido (já usado na linha "
                         f"{ids_vistos[id_.lower()]}).")
        if REGEX_SERVIDOR.match(id_):
            avisos.append(f"Linha {n}: o id '{id_}' indica um servidor (pro Projeto B), no Projeto A "
                          f"ele é tratado como uma tarefa periódica comum.")

        if cor == "":
            cor_ok = cor_padrao(len(cfg.tarefas), cores_vistas)
            avisos.append(f"Linha {n}: cor ausente em '{id_}', usando a cor padrão {cor_ok}.")
        else:
            m = REGEX_COR.match(cor)
            if not m:
                erros.append(f"Linha {n}: cor '{cor}' inválida, use RGB hexadecimal, "
                             f"ex.: F0E0D0.")
                cor_ok = None
            else:
                h = m.group(1).upper()
                cor_ok = "".join(ch * 2 for ch in h) if len(h) == 3 else h

        if ing == "":
            ingresso = 0
            avisos.append(f"Linha {n}: ingresso ausente em '{id_}', usando 0.")
        else:
            ingresso = _inteiro(ing, "ingresso", n, erros, 0)

        duracao = _inteiro(dur, "duracao", n, erros, 1) if dur != "" else None
        if dur == "":
            erros.append(f"Linha {n}: o campo 'duracao' é obrigatório.")

        periodo = None
        if per == "":
            erros.append(f"Linha {n}: o campo 'periodo' é obrigatório.")
        else:
            try:
                periodo = int(per)
            except ValueError:
                erros.append(f"Linha {n}: o campo 'periodo' deve ser um número inteiro "
                             f"(valor recebido: '{per}').")
            else:
                if periodo < 0:
                    erros.append(f"Linha {n}: período negativo ({periodo}) é erro no "
                                 f"Projeto A (tarefas esporádicas são do Projeto B).")
                    periodo = None
        if periodo == 0 and len(erros) == n_erros_antes:
            avisos.append(f"Linha {n}: a tarefa '{id_}' é aperiódica (período 0) e foi "
                          f"IGNORADA: o Projeto A só simula tarefas periódicas.")
            ids_vistos[id_.lower()] = n
            continue

        if pzo == "":
            prazo = periodo if periodo else None
            if periodo:
                avisos.append(f"Linha {n}: prazo ausente em '{id_}', usando o período "
                              f"({periodo}) como prazo.")
        else:
            prazo = _inteiro(pzo, "prazo", n, erros, 1)
        if id_:
            ids_vistos[id_.lower()] = n
        if len(erros) > n_erros_antes:
            continue
        if cor_ok in cores_vistas:
            erros.append(f"Linha {n}: '{id_}' usa a mesma cor de '{cores_vistas[cor_ok]}' "
                         f"({cor_ok}), cada tarefa deve ter uma cor diferente.")
            continue
        cores_vistas.setdefault(cor_ok, id_)
        if duracao > prazo:
            avisos.append(f"Linha {n}: em '{id_}' a duração ({duracao}) é maior que o prazo "
                          f"({prazo}): toda ocorrência perderá o prazo.")
        if eventos:
            n_com_eventos += 1
        cfg.tarefas.append(TCB(id=id_, cor=cor_ok, ingresso=ingresso, duracao=duracao,
                               periodo=periodo, prazo=prazo, eventos=eventos))

    if n_com_eventos:
        avisos.append(f"{n_com_eventos} tarefa(s) possuem lista_eventos: ela é armazenada no "
                      f"TCB, mas só será simulada no Projeto B.")
    if len(linhas) < 2:
        erros.append("O arquivo precisa de ao menos duas linhas: parâmetros do sistema e "
                     "uma tarefa.")
    elif not cfg.tarefas and not erros:
        avisos.append("Todas as tarefas foram ignoradas: não há tarefas periódicas para simular.")
    if erros:
        raise ErroConfig(erros, avisos)

    carga = sum(t.duracao / t.periodo for t in cfg.tarefas)
    if carga > cfg.n_cpus:
        avisos.append(f"Utilização total U = Σ C/T = {carga:.2f} é MAIOR que o número de CPUs "
                      f"({cfg.n_cpus}): carga insustentável em horizonte ilimitado, "
                      f"as dez ocorrências simuladas ainda podem cumprir seus prazos.")
    cfg.avisos = avisos
    return cfg


def exemplo_padrao() -> str:
    """Configuração pequena para experimentar o simulador."""
    return ("EDF;2;2\n"
            "t01;E6194B;0;2;5;5;\n"
            "t02;3CB44B;0;3;7;7;\n"
            "t03;4363D8;1;2;10;8;\n")
