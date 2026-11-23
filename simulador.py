"""Simulação por ticks com histórico reversível."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List

from edicao import EdicaoMixin
from escalonadores import REGISTRO, ContextoEscalonador
from modelo import (CPU, MAX_EXECUCOES, SEMENTE_PADRAO, ConfigSistema, Estado,
                    EstadoSistema, Evento, Ocorrencia, Tick, TipoEvento, chave_natural)


class ErroEscalonador(Exception):
    """Resposta inválida ou falha do escalonador."""


@dataclass
class Foto:
    """Estado salvo de um passo e quantidade de eventos até ele."""

    estado: EstadoSistema
    n_eventos: int


class Simulador(EdicaoMixin):
    """Cuida do relógio, das tarefas, das CPUs e do histórico."""

    def __init__(self, cfg: ConfigSistema, semente: int = SEMENTE_PADRAO):
        """Começa em t = 0. A mesma semente permite repetir os sorteios."""
        self.cfg = cfg
        self.semente = semente
        self.reiniciar()

    def reiniciar(self) -> None:
        """Volta à configuração carregada, sem as edições feitas depois."""
        self.rng = random.Random(self.semente)
        tarefas = {t.id: t.clone() for t in self.cfg.tarefas}
        self.estado = EstadoSistema(
            relogio=0, algoritmo=self.cfg.algoritmo, quantum=self.cfg.quantum,
            tarefas=tarefas, cpus=[CPU(i + 1) for i in range(self.cfg.n_cpus)])

        self.eventos: List[Evento] = []
        self.trace: List[Tick] = []
        self.historico: List[Foto] = []
        self.cursor = 0

        self.estado.rng_estado = self.rng.getstate()
        self._processar_instante()
        self.historico.append(self._foto())

    def _foto(self) -> Foto:
        """Economiza memória reutilizando os TCBs que não mudaram no passo."""
        foto = self.estado.clone()
        if self.historico:
            anterior = self.historico[self.cursor].estado
            for tid, tc in list(foto.tarefas.items()):
                if tc == anterior.tarefas.get(tid):
                    foto.tarefas[tid] = anterior.tarefas[tid]
        return Foto(foto, len(self.eventos))

    def _evento(self, tipo: TipoEvento, tarefa, cpu, texto: str) -> None:
        """registra o que aconteceu no tick atual para a tela e o Gantt."""
        self.eventos.append(Evento(self.estado.relogio, tipo, tarefa, cpu, texto))

    # Consulta e navegação pelo histórico.

    @property
    def relogio(self) -> int:
        """Tempo simulado, em ticks."""
        return self.estado.relogio

    @property
    def ultimo(self) -> int:
        """Índice do último passo já calculado."""
        return len(self.historico) - 1

    @property
    def terminou(self) -> bool:
        """Todas as tarefas completaram dez execuções ou foram encerradas."""
        return all(t.estado is Estado.ENCERRADA for t in self.estado.tarefas.values())

    @property
    def travada(self) -> bool:
        """O modo completo precisa de intervenção se só restam tarefas suspensas."""
        vivas = [t for t in self.estado.tarefas.values() if t.estado is not Estado.ENCERRADA]
        return bool(vivas) and all(t.estado is Estado.SUSPENSA for t in vivas)

    def _ir_para_indice(self, i: int) -> None:
        """restaura também o gerador aleatório para repetir os sorteios."""
        foto = self.historico[i]
        self.estado = foto.estado.clone()
        self.rng.setstate(foto.estado.rng_estado)
        self.cursor = i

    def passo(self) -> bool:
        """Avança um tick (reaproveita o histórico se estivermos no passado)."""
        if self.cursor < self.ultimo:
            self._ir_para_indice(self.cursor + 1)
            return True
        if self.terminou:
            return False
        self._executar_tick()
        self.historico.append(self._foto())
        self.cursor += 1
        return True

    def voltar(self) -> bool:
        """Retrocede um passo (o relógio volta junto)."""
        if self.cursor == 0:
            return False
        self._ir_para_indice(self.cursor - 1)
        return True

    def ir_para(self, t: int) -> int:
        """Vai ao instante t (calculando passos novos se necessário)."""
        t = max(0, int(t))
        if t <= self.ultimo:
            self._ir_para_indice(t)
            return t
        self._ir_para_indice(self.ultimo)
        while self.cursor < t and self.passo():
            pass
        return self.cursor

    def executar_ate_o_fim(self, limite=None) -> str:
        """O limite opcional encerra o lote, não a simulação."""
        while not self.terminou:
            if self.travada:
                return "travada"
            if limite is not None and self.relogio >= limite:
                return "limite"
            self.passo()
        return "terminou"

    def trace_visivel(self) -> List[Tick]:
        """Retorna os ticks até o ponto atual, sem mostrar o futuro salvo."""
        return self.trace[:self.cursor]

    def eventos_visiveis(self) -> List[Evento]:
        """Mostra apenas os eventos que já aconteceram no passo atual."""
        return self.eventos[:self.historico[self.cursor].n_eventos]

    def eventos_do_instante(self, t: int) -> List[Evento]:
        """Filtra os eventos de um instante para a aba Eventos."""
        return [e for e in self.eventos_visiveis() if e.instante == t]

    # Execução de um tick e tratamento do instante seguinte.

    def _executar_tick(self) -> None:
        """Registra a execução em [t, t+1) e consome um tick de cada CPU ocupada."""
        e = self.estado
        t = e.relogio
        ordem = sorted(e.tarefas, key=chave_natural)
        self.trace.append(Tick(
            t, tuple(c.tarefa_id for c in e.cpus),
            tuple(i for i in ordem if e.tarefas[i].estado is Estado.PRONTA),
            tuple(i for i in ordem if e.tarefas[i].estado is Estado.SUSPENSA)))

        for cpu in e.cpus:
            if cpu.tarefa_id is None:
                cpu.ticks_desligada += 1
                continue
            tc = e.tarefas[cpu.tarefa_id]
            o = tc.atual
            if o.inicio is None:
                o.inicio = t
            o.executado += 1
            o.restante -= 1
            tc.tempo_exec += 1
            cpu.ticks_ocupada += 1
            if e.quantum > 0:
                tc.quantum_restante -= 1

        for tc in e.tarefas.values():
            if tc.estado is Estado.PRONTA:
                tc.tempo_espera += 1

        e.relogio = t + 1
        self._processar_instante()

    def _processar_instante(self) -> None:
        """Quem termina exatamente no prazo ainda o cumpre, por isso o término vem antes."""
        self._fase_terminos()
        self._fase_ativacoes()
        self._fase_prazos()
        self._fase_quantum()
        self._fase_escalonar()

    def _fase_terminos(self) -> None:
        """Encerra as ocorrências concluídas e libera suas CPUs."""
        e = self.estado

        for cpu in e.cpus:
            if cpu.tarefa_id is None:
                continue
            tc = e.tarefas[cpu.tarefa_id]
            if tc.restante > 0:
                continue
            o = tc.atual
            o.fim = e.relogio
            tc.concluidas += 1
            resposta = o.fim - o.ativacao
            tc.resposta_total += resposta
            tc.resposta_max = max(tc.resposta_max, resposta)
            cpu.tarefa_id = None
            tc.cpu = None
            e.precisa_escalonar = True
            self._evento(TipoEvento.TERMINO, tc.id, cpu.indice,
                         f"{tc.id} terminou a ocorrência (tempo de resposta = {resposta}) "
                         f"na CPU {cpu.indice}")
            if tc.concluidas >= MAX_EXECUCOES and tc.atual is None:
                tc.estado = Estado.ENCERRADA
                tc.proxima_ativacao = None
                self._evento(TipoEvento.ENCERRAMENTO, tc.id, None,
                             f"{tc.id} encerrada após {MAX_EXECUCOES} execuções")
            elif tc.atual is not None:
                tc.estado = Estado.PRONTA
            else:
                tc.estado = Estado.AGUARDANDO

    def _fase_ativacoes(self) -> None:
        """Cria as ocorrências previstas para este instante."""
        e = self.estado
        t = e.relogio

        for tc in e.tarefas.values():
            if tc.estado is Estado.ENCERRADA or tc.proxima_ativacao is None:
                continue
            if tc.proxima_ativacao > t:
                continue
            o = Ocorrencia(ativacao=t, prazo_abs=t + tc.prazo, restante=tc.duracao, duracao=tc.duracao)
            tc.ocorrencias.append(o)
            tc.ativacoes += 1
            tc.proxima_ativacao = t + tc.periodo if tc.ativacoes < MAX_EXECUCOES else None
            self._evento(TipoEvento.ATIVACAO, tc.id, None,
                         f"{tc.id}: ocorrência {tc.ativacoes} ativada "
                         f"(duração {tc.duracao}, prazo absoluto {o.prazo_abs})")
            if tc.estado in (Estado.NOVA, Estado.AGUARDANDO):
                tc.estado = Estado.PRONTA
                e.precisa_escalonar = True

    def _fase_prazos(self) -> None:
        """Marca as perdas de prazo, mantendo a ocorrência até ela terminar."""
        e = self.estado

        for tc in e.tarefas.values():
            for o in tc.ocorrencias:
                if o.cancelada or o.prazo_tratado or e.relogio < o.prazo_abs:
                    continue
                o.prazo_tratado = True
                if o.fim is None or o.fim > o.prazo_abs:
                    o.perdeu = True
                    tc.perdas_prazo += 1
                    self._evento(TipoEvento.PRAZO_PERDIDO, tc.id, tc.cpu,
                                 f"{tc.id} PERDEU o prazo {o.prazo_abs} (ativada em "
                                 f"{o.ativacao}, faltam {o.restante}). A ocorrência continua executando")
                else:
                    self._evento(TipoEvento.PRAZO, tc.id, None,
                                 f"{tc.id} cumpriu o prazo {o.prazo_abs}")

    def _fase_quantum(self) -> None:
        """quando a fatia acaba, pede outra decisão ao escalonador."""
        e = self.estado
        if e.quantum <= 0:
            return

        for cpu in e.cpus:
            if cpu.tarefa_id and e.tarefas[cpu.tarefa_id].quantum_restante <= 0:
                e.precisa_escalonar = True
                self._evento(TipoEvento.QUANTUM, cpu.tarefa_id, cpu.indice,
                             f"quantum de {cpu.tarefa_id} esgotado na CPU {cpu.indice}: "
                             f"escalonador acionado")

    def _fase_escalonar(self) -> None:
        """roda o escalonador quando precisa e atualiza quais CPUs estão ligadas."""
        e = self.estado
        if e.precisa_escalonar:
            self._escalonar()
        self._atualizar_energia()

    # Escolha das tarefas e distribuição entre as CPUs.

    def _escalonar(self) -> None:
        """pede as tarefas ao algoritmo e distribui as escolhidas pelas CPUs."""
        e = self.estado
        e.precisa_escalonar = False
        candidatas = [t for t in e.tarefas.values()
                      if t.estado in (Estado.PRONTA, Estado.EXECUTANDO)]
        funcao = REGISTRO[e.algoritmo]
        ctx = ContextoEscalonador(e.relogio, self.rng)
        try:
            escolhidas = list(funcao(candidatas, len(e.cpus), ctx))
        except Exception as exc:
            raise ErroEscalonador(f"O escalonador '{e.algoritmo}' falhou: {exc}") from exc
        if ctx.sorteadas:
            e.rng_estado = self.rng.getstate()

        ids = [t.id for t in escolhidas]
        if (len(set(ids)) != len(ids) or len(ids) != min(len(candidatas), len(e.cpus))
                or any(t not in candidatas for t in escolhidas)):
            raise ErroEscalonador(f"O escalonador '{e.algoritmo}' devolveu uma escolha "
                                  f"inválida: {ids}")

        for tc in ctx.sorteadas:
            self._evento(TipoEvento.SORTEIO, tc.id, None,
                         f"empate total entre tarefas: {tc.id} escolhida por sorteio")

        # Quem perdeu a disputa volta à fila de prontos.
        for cpu in e.cpus:
            if cpu.tarefa_id and cpu.tarefa_id not in ids:
                tc = e.tarefas[cpu.tarefa_id]
                tc.estado = Estado.PRONTA
                tc.cpu = None
                tc.preempcoes += 1
                self._evento(TipoEvento.PREEMPCAO, tc.id, cpu.indice,
                             f"{tc.id} perdeu a CPU {cpu.indice} (preempção)")
                cpu.tarefa_id = None

        for cpu in e.cpus:
            if cpu.tarefa_id and e.quantum > 0:
                tc = e.tarefas[cpu.tarefa_id]
                if tc.quantum_restante <= 0:
                    tc.quantum_restante = e.quantum

        # Se a última CPU estiver livre, evita uma migração desnecessária.
        livres = [c for c in e.cpus if c.tarefa_id is None]
        for tc in escolhidas:
            if tc.estado is Estado.EXECUTANDO:
                continue
            cpu = next((c for c in livres if c.indice == tc.ultima_cpu), livres[0])
            livres.remove(cpu)
            self._despachar(tc, cpu)

    def _despachar(self, tc, cpu: CPU) -> None:
        """Coloca a tarefa na CPU e registra a troca ou a migração."""
        e = self.estado
        migrou = tc.ultima_cpu is not None and tc.ultima_cpu != cpu.indice
        tc.estado = Estado.EXECUTANDO
        tc.cpu = cpu.indice
        cpu.tarefa_id = tc.id
        cpu.ultima_tarefa_id = tc.id
        cpu.trocas_contexto += 1
        tc.quantum_restante = e.quantum
        self._evento(TipoEvento.DESPACHO, tc.id, cpu.indice,
                     f"{tc.id} despachada na CPU {cpu.indice} (troca de contexto)")
        if migrou:
            tc.migracoes += 1
            self._evento(TipoEvento.MIGRACAO, tc.id, cpu.indice,
                         f"{tc.id} migrou da CPU {tc.ultima_cpu} para a CPU {cpu.indice}")
        tc.ultima_cpu = cpu.indice

    def _atualizar_energia(self) -> None:
        """desliga CPUs sem tarefa e liga as que receberam trabalho."""
        e = self.estado

        for cpu in e.cpus:
            ocupada = cpu.tarefa_id is not None
            if ocupada and not cpu.ligada:
                cpu.ligada, cpu.desde = True, e.relogio
                self._evento(TipoEvento.CPU_LIGA, None, cpu.indice,
                             f"CPU {cpu.indice} ligada")
            elif not ocupada and cpu.ligada:
                cpu.ligada, cpu.desde = False, e.relogio
                self._evento(TipoEvento.CPU_DESLIGA, None, cpu.indice,
                             f"CPU {cpu.indice} desligada (nenhuma tarefa para executar)")

    def estatisticas(self) -> Dict[str, list]:
        """Reúne os totais por tarefa e CPU usados na tela e no terminal."""
        e = self.estado
        tarefas = []
        for tc in sorted(e.tarefas.values(), key=lambda t: chave_natural(t.id)):
            media = tc.resposta_total / tc.concluidas if tc.concluidas else 0.0
            tarefas.append(dict(id=tc.id, ativacoes=tc.ativacoes, concluidas=tc.concluidas,
                                perdas=tc.perdas_prazo, preempcoes=tc.preempcoes,
                                migracoes=tc.migracoes, exec=tc.tempo_exec,
                                espera=tc.tempo_espera, resp_max=tc.resposta_max,
                                resp_media=media))

        cpus = []
        for c in e.cpus:
            total = c.ticks_ocupada + c.ticks_desligada
            cpus.append(dict(indice=c.indice, ocupada=c.ticks_ocupada,
                             desligada=c.ticks_desligada, trocas=c.trocas_contexto,
                             uso=(100.0 * c.ticks_ocupada / total) if total else 0.0))
        return dict(tarefas=tarefas, cpus=cpus)
