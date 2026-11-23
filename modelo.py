"""Estruturas de tarefas, processadores e histórico."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

MAX_EXECUCOES = 10
MAX_CPUS = 1024  # Limita o consumo de memória do histórico e do Gantt.
QUANTUM_PADRAO = 2
CPUS_PADRAO = 1
ALGORITMO_PADRAO = "EDF"
SEMENTE_PADRAO = 2026  # Mantém os sorteios reproduzíveis.

PALETA = ["E6194B", "3CB44B", "4363D8", "F58231", "911EB4", "42D4F4", "F032E6",
          "BFEF45", "469990", "9A6324", "FFE119", "800000", "808000", "000075"]


class Estado(Enum):
    """Estados que uma tarefa pode assumir na simulação."""

    NOVA = "nova (ainda não ingressou)"
    PRONTA = "pronta"
    EXECUTANDO = "executando"
    SUSPENSA = "suspensa"
    AGUARDANDO = "aguardando próximo período"
    ENCERRADA = "encerrada"


class TipoEvento(Enum):
    """Acontecimentos mostrados no registro de eventos e no Gantt."""

    ATIVACAO = "ativação (entra na fila de prontos)"
    TERMINO = "término de ocorrência"
    ENCERRAMENTO = "tarefa encerrada"
    PRAZO = "prazo cumprido"
    PRAZO_PERDIDO = "prazo perdido"
    PREEMPCAO = "preempção"
    DESPACHO = "despacho (troca de contexto)"
    MIGRACAO = "migração de CPU"
    SORTEIO = "sorteio (desempate)"
    QUANTUM = "quantum esgotado (escalonador chamado)"
    SUSPENSAO = "suspensão"
    RETOMADA = "retomada"
    MODIFICACAO = "modificação manual"
    CPU_DESLIGA = "CPU desligada"
    CPU_LIGA = "CPU ligada"


class ErroEdicao(Exception):
    """Alteração inválida na simulação."""


@dataclass
class Ocorrencia:
    """Uma execução periódica, com seu próprio prazo e tempo restante."""

    ativacao: int
    prazo_abs: int
    restante: int

    inicio: Optional[int] = None
    fim: Optional[int] = None
    prazo_tratado: bool = False
    perdeu: bool = False
    duracao: int = 0
    executado: int = 0
    cancelada: bool = False


@dataclass
class TCB:
    """Reúne os dados, as ocorrências e as estatísticas de uma tarefa."""

    # Dados da configuração.
    id: str
    cor: str
    ingresso: int
    duracao: int
    periodo: int
    prazo: int
    eventos: Tuple[str, ...] = ()

    # Situação atual e ocorrências, inclusive as já concluídas.
    estado: Estado = Estado.NOVA
    cpu: Optional[int] = None
    ultima_cpu: Optional[int] = None
    ocorrencias: List[Ocorrencia] = field(default_factory=list)
    ativacoes: int = 0
    proxima_ativacao: Optional[int] = None
    concluidas: int = 0
    quantum_restante: int = 0

    # Totais usados nas tabelas de resumo.
    perdas_prazo: int = 0
    preempcoes: int = 0
    migracoes: int = 0
    tempo_exec: int = 0
    tempo_espera: int = 0
    resposta_max: int = 0
    resposta_total: int = 0

    def __post_init__(self):
        """a primeira ativação acontece no instante de ingresso."""
        if self.proxima_ativacao is None and self.ativacoes == 0:
            self.proxima_ativacao = self.ingresso

    @property
    def atual(self) -> Optional[Ocorrencia]:
        """Se houver ocorrências acumuladas, atende primeiro a mais antiga."""
        for o in self.ocorrencias:
            if o.fim is None and not o.cancelada:
                return o
        return None

    @property
    def restante(self) -> int:
        """Tempo que falta para a ocorrência atual terminar."""
        o = self.atual
        return o.restante if o else 0

    @property
    def prazo_abs(self) -> Optional[int]:
        """Instante de ativação mais o prazo relativo da ocorrência atual."""
        o = self.atual
        return o.prazo_abs if o else None

    def clone(self) -> "TCB":
        """Copia também as ocorrências para isolar os estados do histórico."""
        c = copy.copy(self)
        c.ocorrencias = [copy.copy(o) for o in self.ocorrencias]
        return c


@dataclass
class CPU:
    """Um processador."""

    indice: int
    ligada: bool = True
    tarefa_id: Optional[str] = None
    ultima_tarefa_id: Optional[str] = None

    ticks_ocupada: int = 0
    ticks_desligada: int = 0
    trocas_contexto: int = 0
    desde: int = 0

    def clone(self) -> "CPU":
        """Cada passo do histórico precisa de sua própria cópia da CPU."""
        return copy.copy(self)


@dataclass
class EstadoSistema:
    """Estado do sistema que será guardado no histórico."""

    relogio: int
    algoritmo: str
    quantum: int
    tarefas: Dict[str, TCB]
    cpus: List[CPU]
    precisa_escalonar: bool = True
    rng_estado: object = None

    def clone(self) -> "EstadoSistema":
        """Copia tarefas e CPUs para que uma edição não altere o passado."""
        return EstadoSistema(
            relogio=self.relogio, algoritmo=self.algoritmo, quantum=self.quantum,
            tarefas={k: v.clone() for k, v in self.tarefas.items()},
            cpus=[c.clone() for c in self.cpus],
            precisa_escalonar=self.precisa_escalonar, rng_estado=self.rng_estado)


@dataclass(frozen=True)
class Evento:
    """Acontecimento com instante, tarefa e CPU, usado no registro e no Gantt."""

    instante: int
    tipo: TipoEvento
    tarefa: Optional[str]
    cpu: Optional[int]
    texto: str


@dataclass(frozen=True)
class Tick:
    """Registro da execução no intervalo [t, t+1)."""

    t: int
    cpus: Tuple[Optional[str], ...]
    prontas: Tuple[str, ...]
    suspensas: Tuple[str, ...]


@dataclass
class ConfigSistema:
    """Resultado do carregamento do arquivo de configuração."""

    algoritmo: str = ALGORITMO_PADRAO
    quantum: int = QUANTUM_PADRAO
    n_cpus: int = CPUS_PADRAO
    tarefas: List[TCB] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)
    origem: str = ""


def chave_natural(texto: str):
    """Ordena IDs com números como esperamos, colocando t2 antes de t10."""
    return [(0, int(p), "") if p.isdigit() else (1, 0, p.lower())
            for p in re.split(r"(\d+)", texto) if p != ""]


def cor_padrao(indice: int, usadas=()) -> str:
    """Busca uma cor livre, mesmo quando as cores da paleta já foram usadas."""
    usadas = set(usadas)
    for cor in PALETA[indice:] + PALETA[:indice]:
        if cor not in usadas:
            return cor
    # O incremento ímpar percorre o espaço RGB sem repetir.
    for i in range(1, 1 << 24):
        cor = f"{(i * 0x9E3779) & 0xFFFFFF:06X}"
        if cor not in usadas:
            return cor
    raise ValueError("Não há cores RGB livres.")


def cor_texto_sobre(cor_hex: str) -> str:
    """Escolhe texto preto ou branco para dar contraste com o fundo."""
    r, g, b = (int(cor_hex[i:i + 2], 16) for i in (0, 2, 4))
    return "#000000" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "#FFFFFF"
