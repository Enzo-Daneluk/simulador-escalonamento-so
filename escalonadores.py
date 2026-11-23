"""Políticas de escalonamento e desempates."""

from __future__ import annotations

import importlib.util
import os
import random
from typing import Callable, Dict, List

from modelo import Estado, TCB, TipoEvento, chave_natural

REGISTRO: Dict[str, Callable] = {}


def escalonador(nome: str):
    """Registra a função pelo nome do algoritmo, sem diferenciar maiúsculas."""

    def registrar(funcao):
        """Associa o nome à função que escolhe as tarefas."""
        REGISTRO[nome.upper()] = funcao
        return funcao

    return registrar


def nomes_disponiveis() -> List[str]:
    """Nomes dos algoritmos registrados (RM, EDF e os carregados por plugin)."""
    return sorted(REGISTRO)


class ContextoEscalonador:
    """Reúne o que as políticas usam para desempatar e sortear tarefas."""

    def __init__(self, relogio: int, rng: random.Random):
        """Guarda os sorteios para que o Gantt possa marcá-los depois."""
        self.relogio = relogio
        self.rng = rng
        self.sorteadas: List[TCB] = []

    def selecionar(self, candidatas: List[TCB], n_cpus: int, prioridade: Callable) -> List[TCB]:
        """Escolhe as tarefas por prioridade e resolve os empates."""

        def chave(t: TCB):
            """Compara prioridade, execução anterior, prazo, ingresso e duração."""
            o = t.atual
            return (prioridade(t),
                    0 if t.estado is Estado.EXECUTANDO else 1,  # prefere continuar
                    o.prazo_abs,
                    t.ingresso,  # ingresso da tarefa, não da ocorrência
                    o.duracao or t.duracao)

        # ID estabiliza a entrada do sorteio, e não desempata a prioridade.
        ordenadas = sorted(candidatas, key=lambda t: (chave(t), chave_natural(t.id)))
        escolhidas: List[TCB] = []
        i = 0
        while i < len(ordenadas) and len(escolhidas) < n_cpus:
            j = i
            while j < len(ordenadas) and chave(ordenadas[j]) == chave(ordenadas[i]):
                j += 1

            grupo = ordenadas[i:j]
            vagas = n_cpus - len(escolhidas)
            if len(grupo) <= vagas:
                escolhidas.extend(grupo)
            else:
                sorteadas = self.rng.sample(grupo, vagas)
                self.sorteadas.extend(sorteadas)
                escolhidas.extend(sorteadas)
            i = j

        return escolhidas


@escalonador("RM")
def rate_monotonic(candidatas: List[TCB], n_cpus: int, ctx: ContextoEscalonador) -> List[TCB]:
    """No RM, quem tem o menor período tem maior prioridade."""
    return ctx.selecionar(candidatas, n_cpus, lambda t: t.periodo)


@escalonador("EDF")
def earliest_deadline_first(candidatas: List[TCB], n_cpus: int,
                            ctx: ContextoEscalonador) -> List[TCB]:
    """No EDF, quem tem o prazo absoluto mais próximo tem maior prioridade."""
    return ctx.selecionar(candidatas, n_cpus, lambda t: t.prazo_abs)


def carregar_plugin(caminho: str) -> List[str]:
    """Carrega políticas registradas por @escalonador em um arquivo externo."""
    if not os.path.isfile(caminho):
        raise FileNotFoundError(f"Arquivo de escalonador não encontrado: {caminho}")
    antes = set(REGISTRO)
    nome_modulo = "plugin_" + os.path.splitext(os.path.basename(caminho))[0]
    spec = importlib.util.spec_from_file_location(nome_modulo, caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return sorted(set(REGISTRO) - antes)
