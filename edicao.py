"""Edição das tarefas e do sistema durante a simulação."""

from __future__ import annotations

from typing import Optional, Tuple

from escalonadores import REGISTRO
from modelo import (CPU, MAX_CPUS, TCB, ErroEdicao, Estado, TipoEvento, cor_padrao)
import config


class EdicaoMixin:
    """Métodos de edição usados pela classe Simulador."""

    def _tarefa(self, id_: str) -> TCB:
        """Busca o ID sem diferenciar maiúsculas e avisa se a tarefa não existe."""
        tc = self.estado.tarefas.get(id_)
        if tc is None:
            for outro in self.estado.tarefas.values():
                if outro.id.lower() == str(id_).lower():
                    return outro
            raise ErroEdicao(f"A tarefa '{id_}' não existe no sistema.")
        return tc

    @staticmethod
    def _inteiro(valor, nome: str, minimo: int) -> int:
        """Confere o valor mínimo e informa qual campo está inválido."""
        try:
            numero = int(str(valor).strip())
        except ValueError:
            raise ErroEdicao(f"O campo '{nome}' deve ser um número inteiro "
                             f"(valor recebido: '{valor}').")
        if numero < minimo:
            raise ErroEdicao(f"O campo '{nome}' deve ser maior ou igual a {minimo} "
                             f"(valor recebido: {numero}).")
        return numero

    @staticmethod
    def _cor(valor: str) -> str:
        """Confere a cor e devolve o RGB em maiúsculas, sem o sinal #."""
        m = config.REGEX_COR.match(str(valor).strip())
        if not m:
            raise ErroEdicao(f"Cor '{valor}' inválida: use RGB hexadecimal, ex.: F0E0D0.")
        h = m.group(1).upper()
        return "".join(c * 2 for c in h) if len(h) == 3 else h

    def _iniciar_edicao(self) -> None:
        """Depois de validar, descarta os passos futuros que dependiam do estado antigo."""
        c = self.cursor
        n_ev = self.historico[c].n_eventos
        del self.historico[c + 1:]
        del self.trace[c:]
        del self.eventos[n_ev:]

    def _concluir_edicao(self, tipo: TipoEvento, tarefa: Optional[str], texto: str) -> None:
        """registra a mudança e refaz o escalonamento no mesmo tick."""
        self._evento(tipo, tarefa, None, texto)
        self.estado.precisa_escalonar = True
        self._processar_instante()
        self.historico[self.cursor] = self._foto()

    def _liberar_cpu(self, tc: TCB) -> None:
        """Libera a CPU da tarefa para uma nova escolha do escalonador."""
        for cpu in self.estado.cpus:
            if cpu.tarefa_id == tc.id:
                cpu.tarefa_id = None
        tc.cpu = None

    def _cor_disponivel(self, cor, propria=None):
        """confere se outra tarefa já usa essa cor."""
        for tc in self.estado.tarefas.values():
            if tc.id != propria and tc.cor == cor:
                raise ErroEdicao(f"A cor {cor} já pertence à tarefa {tc.id}, escolha outra cor.")
        return cor

    def suspender(self, id_: str) -> None:
        """Retira a tarefa da CPU e da fila de prontos até ela ser retomada."""
        tc = self._tarefa(id_)
        if tc.estado is Estado.ENCERRADA:
            raise ErroEdicao(f"{tc.id} já foi encerrada: não é possível suspendê-la.")
        if tc.estado is Estado.SUSPENSA:
            raise ErroEdicao(f"{tc.id} já está suspensa.")

        self._iniciar_edicao()
        if tc.estado is Estado.EXECUTANDO:
            self._liberar_cpu(tc)
        tc.estado = Estado.SUSPENSA
        self._concluir_edicao(TipoEvento.SUSPENSAO, tc.id, f"{tc.id} suspensa manualmente")

    def retomar(self, id_: str) -> None:
        """A tarefa suspensa volta a disputar CPU neste mesmo instante."""
        tc = self._tarefa(id_)
        if tc.estado is not Estado.SUSPENSA:
            raise ErroEdicao(f"{tc.id} não está suspensa (estado atual: {tc.estado.value}): "
                             f"só tarefas suspensas podem ser retomadas.")

        self._iniciar_edicao()
        if tc.atual is not None:
            tc.estado = Estado.PRONTA
        else:
            tc.estado = Estado.NOVA if tc.ativacoes == 0 else Estado.AGUARDANDO
        self._concluir_edicao(TipoEvento.RETOMADA, tc.id, f"{tc.id} retomada manualmente")

    def encerrar_tarefa(self, id_: str) -> None:
        """Cancela as ocorrências pendentes, mantendo as conclusões já registradas."""
        tc = self._tarefa(id_)
        if tc.estado is Estado.ENCERRADA:
            raise ErroEdicao(f"{tc.id} já está encerrada.")

        self._iniciar_edicao()
        if tc.estado is Estado.EXECUTANDO:
            self._liberar_cpu(tc)
        tc.estado = Estado.ENCERRADA
        for o in tc.ocorrencias:
            if o.fim is None:
                o.cancelada = True
        tc.proxima_ativacao = None
        self._evento(TipoEvento.ENCERRAMENTO, tc.id, None, f"{tc.id} encerrada manualmente")
        self._concluir_edicao(TipoEvento.MODIFICACAO, tc.id, f"{tc.id} removida do escalonamento")

    def definir_restante(self, id_: str, valor) -> None:
        """Muda o tempo que falta para a ocorrência atual terminar."""
        tc = self._tarefa(id_)
        v = self._inteiro(valor, "tempo restante", 1)
        if tc.atual is None:
            raise ErroEdicao(f"{tc.id} não tem ocorrência em andamento (estado: "
                             f"{tc.estado.value}). Não há tempo restante para alterar.")
        antigo = tc.atual.restante

        self._iniciar_edicao()
        tc.atual.restante = v
        tc.atual.duracao = tc.atual.executado + v
        self._concluir_edicao(TipoEvento.MODIFICACAO, tc.id,
                              f"{tc.id}: tempo restante alterado de {antigo} para {v}")


    def editar_tarefa(self, id_: str, cor=None, ingresso=None, duracao=None, periodo=None,
                      prazo=None, eventos: Optional[Tuple[str, ...]] = None) -> None:
        """Valida todas as mudanças antes de mexer na tarefa ou no histórico."""
        tc = self._tarefa(id_)
        novos = {}
        if cor not in (None, ""):
            c = self._cor_disponivel(self._cor(cor), tc.id)
            if c != tc.cor:
                novos["cor"] = c
        for nome, valor, minimo in (("ingresso", ingresso, 0), ("duracao", duracao, 1),
                                    ("periodo", periodo, 1), ("prazo", prazo, 1)):
            if valor not in (None, ""):
                if nome == "periodo" and str(valor).strip() == "0":
                    raise ErroEdicao("Período 0 indica tarefa aperiódica, que só será "
                                     "suportada no Projeto B.")
                v = self._inteiro(valor, nome, minimo)
                if v != getattr(tc, nome):
                    novos[nome] = v
        if eventos is not None and tuple(eventos) != tc.eventos:
            novos["eventos"] = tuple(eventos)
        if not novos:
            raise ErroEdicao("Nenhuma alteração: os valores informados são iguais aos atuais.")
        if tc.estado is Estado.ENCERRADA and set(novos) - {"cor"}:
            raise ErroEdicao(f"{tc.id} já foi encerrada: apenas a cor pode ser alterada.")
        if "ingresso" in novos:
            if not (tc.estado is Estado.NOVA and tc.ativacoes == 0):
                raise ErroEdicao(f"{tc.id} já ingressou no sistema (ingresso em {tc.ingresso}): "
                                 f"o ingresso só pode mudar antes da primeira ativação.")
            if novos["ingresso"] < self.relogio:
                raise ErroEdicao(f"O novo ingresso ({novos['ingresso']}) está no passado "
                                 f"(relógio = {self.relogio}). Use um valor ≥ {self.relogio}.")

        descricao = ", ".join(f"{k}: {getattr(tc, k)} → {v}" for k, v in novos.items())

        self._iniciar_edicao()
        for k, v in novos.items():
            setattr(tc, k, v)
        if "ingresso" in novos:
            tc.proxima_ativacao = novos["ingresso"]
        # duração e prazo editados só valem para novas ocorrências.
        # Preserva a próxima ativação, o novo período vale depois dela.
        self._concluir_edicao(TipoEvento.MODIFICACAO, tc.id,
                              f"{tc.id} modificada ({descricao}). "
                              f"Duração e prazo valem para novas ocorrências. "
                              f"O período vale após "
                              f"a próxima ativação já agendada")

    def adicionar_tarefa(self, id_: str, cor=None, ingresso=0, duracao=1, periodo=1,
                         prazo=None, eventos: Tuple[str, ...] = ()) -> None:
        """Cria uma tarefa com ingresso no presente ou no futuro."""
        id_ = (id_ or "").strip()
        if not id_ or ";" in id_:
            raise ErroEdicao("Preencha o id da tarefa sem usar ponto e vírgula.")
        if any(t.id.lower() == id_.lower() for t in self.estado.tarefas.values()):
            raise ErroEdicao(f"Já existe uma tarefa com o id '{id_}'.")
        c = self._cor(cor) if cor not in (None, "") else cor_padrao(
            len(self.estado.tarefas), (t.cor for t in self.estado.tarefas.values()))
        self._cor_disponivel(c)
        ing = self._inteiro(ingresso, "ingresso", 0)
        if ing < self.relogio:
            raise ErroEdicao(f"O ingresso ({ing}) está no passado (relógio = {self.relogio}): "
                             f"não é possível criar uma tarefa retroativamente.")
        dur = self._inteiro(duracao, "duracao", 1)
        if str(periodo).strip() == "0":
            raise ErroEdicao("Período 0 indica tarefa aperiódica, que só será suportada no "
                             "Projeto B.")
        per = self._inteiro(periodo, "periodo", 1)
        pzo = per if prazo in (None, "") else self._inteiro(prazo, "prazo", 1)

        self._iniciar_edicao()
        self.estado.tarefas[id_] = TCB(id=id_, cor=c, ingresso=ing, duracao=dur, periodo=per,
                                       prazo=pzo, eventos=tuple(eventos))
        self._concluir_edicao(TipoEvento.MODIFICACAO, id_,
                              f"tarefa {id_} adicionada (ingresso {ing}, C={dur}, T={per}, D={pzo})")

    def definir_sistema(self, algoritmo=None, quantum=None, n_cpus=None) -> None:
        """Valida e altera algoritmo, quantum ou quantidade de CPUs."""
        e = self.estado
        mudancas = []
        alg = None
        if algoritmo not in (None, ""):
            alg = str(algoritmo).strip().upper()
            if alg not in REGISTRO:
                raise ErroEdicao(f"Algoritmo '{algoritmo}' desconhecido. Disponíveis: "
                                 f"{', '.join(sorted(REGISTRO))}.")
            if alg != e.algoritmo:
                mudancas.append(f"algoritmo {e.algoritmo} → {alg}")
            else:
                alg = None

        q = None
        if quantum not in (None, ""):
            q = self._inteiro(quantum, "quantum", 0)
            if q != e.quantum:
                mudancas.append(f"quantum {e.quantum} → {q}")
            else:
                q = None

        m = None
        if n_cpus not in (None, ""):
            m = self._inteiro(n_cpus, "qtde_cpus", 1)
            if m > MAX_CPUS:
                raise ErroEdicao(f"qtde_cpus={m} passa do limite de CPUs do simulador "
                                 f"({MAX_CPUS}).")
            if m != len(e.cpus):
                mudancas.append(f"CPUs {len(e.cpus)} → {m}")
            else:
                m = None

        if not mudancas:
            raise ErroEdicao("Nenhuma alteração: os valores informados são iguais aos atuais.")

        self._iniciar_edicao()
        if alg is not None:
            e.algoritmo = alg
        if q is not None:
            e.quantum = q
            for tc in e.tarefas.values():
                if tc.estado is Estado.EXECUTANDO:
                    tc.quantum_restante = q
        if m is not None:
            if m < len(e.cpus):
                for cpu in e.cpus[m:]:
                    if cpu.tarefa_id:
                        tc = e.tarefas[cpu.tarefa_id]
                        tc.estado, tc.cpu = Estado.PRONTA, None
                        tc.preempcoes += 1
                        self._evento(TipoEvento.PREEMPCAO, tc.id, cpu.indice,
                                     f"{tc.id} perdeu a CPU {cpu.indice} (CPU removida)")
                del e.cpus[m:]
            else:
                e.cpus.extend(CPU(i + 1, desde=e.relogio) for i in range(len(e.cpus), m))
        self._concluir_edicao(TipoEvento.MODIFICACAO, None, "sistema: " + ", ".join(mudancas))
