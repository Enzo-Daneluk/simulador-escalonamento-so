"""Formulários de configuração e edição."""

from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, ttk

from escalonadores import nomes_disponiveis
from modelo import MAX_CPUS, ErroEdicao, Estado, QUANTUM_PADRAO, chave_natural, cor_padrao


class DialogoBase(tk.Toplevel):
    """Base dos formulários, com mensagem de erro e botões de confirmação."""

    def __init__(self, pai, titulo: str, sim, ao_aplicar):
        """Monta o formulário e os botões Aplicar e Cancelar."""
        super().__init__(pai)
        self.title(titulo)
        self.sim = sim
        self.ao_aplicar = ao_aplicar
        self.resizable(False, False)

        self.corpo = ttk.Frame(self, padding=12)
        self.corpo.pack(fill="both", expand=True)

        self.erro = tk.StringVar()
        self.lbl_erro = tk.Label(self, textvariable=self.erro, fg="#B00020", wraplength=420,
                                 justify="left", anchor="w")
        rodape = ttk.Frame(self, padding=(12, 0, 12, 12))
        self.lbl_erro.pack(fill="x", padx=12)
        rodape.pack(fill="x")
        ttk.Button(rodape, text="Aplicar", command=self._aplicar).pack(side="right")
        ttk.Button(rodape, text="Cancelar", command=self.destroy).pack(side="right", padx=6)

        self.bind("<Return>", lambda _e: self._aplicar())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.transient(pai)

    def mostrar(self):
        """Mantém o foco no formulário até ele ser fechado."""
        self.update_idletasks()
        self.grab_set()
        self.focus_set()

    def _aplicar(self):
        """tenta aplicar a mudança e mostra o motivo se ela for recusada."""
        try:
            self.aplicar()
        except ErroEdicao as exc:
            self.erro.set("Não foi possível aplicar: " + str(exc))
            return
        self.ao_aplicar()
        self.destroy()

    def aplicar(self):
        """Cada diálogo implementa aqui a modificação que ele faz."""
        raise NotImplementedError

    def linha(self, rotulo: str, widget_fabrica, linha: int, dica: str = ""):
        """Coloca o rótulo, o campo e uma dica na mesma linha."""
        ttk.Label(self.corpo, text=rotulo).grid(row=linha, column=0, sticky="w", pady=3)
        w = widget_fabrica(self.corpo)
        w.grid(row=linha, column=1, sticky="we", pady=3, padx=(8, 0))
        if dica:
            ttk.Label(self.corpo, text=dica, foreground="#666").grid(
                row=linha, column=2, sticky="w", padx=(8, 0))
        return w


class DialogoSistema(DialogoBase):
    """Formulário para alterar algoritmo, quantum e quantidade de CPUs."""

    def __init__(self, pai, sim, ao_aplicar):
        """Campos preenchidos com os valores atuais do sistema."""
        super().__init__(pai, "Sistema simulado", sim, ao_aplicar)
        e = sim.estado
        self.alg = tk.StringVar(value=e.algoritmo)
        self.q = tk.StringVar(value=str(e.quantum))
        self.m = tk.StringVar(value=str(len(e.cpus)))
        self.linha("Algoritmo:", lambda p: ttk.Combobox(
            p, textvariable=self.alg, values=nomes_disponiveis(), state="readonly", width=14), 0,
            "vale a partir deste instante")
        self.linha("Quantum (ticks):", lambda p: ttk.Spinbox(
            p, from_=0, to=100000, textvariable=self.q, width=10), 1, "0 = sem fatia de tempo")
        self.linha("Nº de CPUs:", lambda p: ttk.Spinbox(
            p, from_=1, to=MAX_CPUS, textvariable=self.m, width=10), 2,
            f"1 a {MAX_CPUS}")

        self.mostrar()

    def aplicar(self):
        """O simulador recebe os valores e confere se a mudança é válida."""
        self.sim.definir_sistema(self.alg.get(), self.q.get(), self.m.get())


class DialogoTarefa(DialogoBase):
    """Formulário compartilhado pela criação e pela edição de tarefas."""

    def __init__(self, pai, sim, ao_aplicar, tarefa=None):
        """Na edição, mantém o ID fixo e bloqueia o ingresso após a primeira ativação."""
        super().__init__(pai, "Adicionar tarefa" if tarefa is None else f"Editar {tarefa.id}",
                         sim, ao_aplicar)
        self.tarefa = tarefa
        n = len(sim.estado.tarefas)
        t = tarefa
        self.v = {
            "id": tk.StringVar(value=t.id if t else f"t{n + 1:02d}"),
            "cor": tk.StringVar(value=t.cor if t else cor_padrao(
                n, (x.cor for x in sim.estado.tarefas.values()))),
            "ingresso": tk.StringVar(value=str(t.ingresso if t else sim.relogio)),
            "duracao": tk.StringVar(value=str(t.duracao if t else 1)),
            "periodo": tk.StringVar(value=str(t.periodo if t else 5)),
            "prazo": tk.StringVar(value=str(t.prazo if t else "")),
            "eventos": tk.StringVar(value=";".join(t.eventos) if t else ""),
        }

        e_id = self.linha("ID:", lambda p: ttk.Entry(p, textvariable=self.v["id"], width=16), 0,
                          "não pode ser alterado" if t else "único")
        if t:
            e_id.state(["disabled"])

        quadro = ttk.Frame(self.corpo)
        ttk.Entry(quadro, textvariable=self.v["cor"], width=9).pack(side="left")
        self.amostra = tk.Label(quadro, width=3, bg="#" + self.v["cor"].get())
        self.amostra.pack(side="left", padx=4)
        ttk.Button(quadro, text="Escolher…", command=self._escolher_cor).pack(side="left")
        ttk.Label(self.corpo, text="Cor (RGB hex):").grid(row=1, column=0, sticky="w", pady=3)
        quadro.grid(row=1, column=1, sticky="w", pady=3, padx=(8, 0))

        e_ing = self.linha("Ingresso:", lambda p: ttk.Entry(p, textvariable=self.v["ingresso"], width=16), 2,
                           "instante da 1ª ativação")
        if t and not (t.estado is Estado.NOVA and t.ativacoes == 0):
            e_ing.state(["disabled"])

        self.linha("Duração (C):", lambda p: ttk.Entry(p, textvariable=self.v["duracao"], width=16), 3,
                   "vale p/ próximas ativações")
        self.linha("Período (T):", lambda p: ttk.Entry(p, textvariable=self.v["periodo"], width=16), 4,
                   "> 0 (periódica)")
        self.linha("Prazo (D):", lambda p: ttk.Entry(p, textvariable=self.v["prazo"], width=16), 5,
                   "vazio = período, vale nas próximas ocorrências")
        self.linha("lista_eventos:", lambda p: ttk.Entry(p, textvariable=self.v["eventos"], width=16), 6,
                   "guardada (Projeto B)")

        self.mostrar()

    def _escolher_cor(self):
        """abre o seletor de cores do sistema e grava o RGB escolhido no campo."""
        r = colorchooser.askcolor(color="#" + self.v["cor"].get(), parent=self)
        if r and r[1]:
            self.v["cor"].set(r[1][1:].upper())
            self.amostra.configure(bg=r[1])

    def aplicar(self):
        """Lê os campos e pede ao simulador para criar ou editar a tarefa."""
        v = {k: x.get().strip() for k, x in self.v.items()}
        evs = tuple(e.strip() for e in v["eventos"].split(";") if e.strip())
        if self.tarefa is None:
            self.sim.adicionar_tarefa(v["id"], v["cor"], v["ingresso"], v["duracao"], v["periodo"],
                                      v["prazo"] or None, evs)
        else:
            ing = v["ingresso"] if str(self.tarefa.ingresso) != v["ingresso"] else None
            self.sim.editar_tarefa(self.tarefa.id, cor=v["cor"], ingresso=ing, duracao=v["duracao"],
                                   periodo=v["periodo"], prazo=v["prazo"] or v["periodo"], eventos=evs)


class DialogoEstado(DialogoBase):
    """Permite suspender, retomar, encerrar ou ajustar o restante."""

    def __init__(self, pai, sim, ao_aplicar, tarefa_id=None):
        """Prepara a seleção da tarefa e das mudanças de estado disponíveis."""
        super().__init__(pai, "Estado da tarefa", sim, ao_aplicar)
        ids = sorted(sim.estado.tarefas, key=chave_natural)
        self.tid = tk.StringVar(value=tarefa_id or (ids[0] if ids else ""))
        self.acao = tk.StringVar(value="suspender")
        self.rest = tk.StringVar(value="1")
        self.info = tk.StringVar()
        self.linha("Tarefa:", lambda p: ttk.Combobox(p, textvariable=self.tid, values=ids,
                                                     state="readonly", width=14), 0)
        ttk.Label(self.corpo, textvariable=self.info, foreground="#444").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(0, 6))
        for i, (valor, texto) in enumerate((("suspender", "Suspender (bloqueia a tarefa, libera a CPU)"),
                                            ("retomar", "Retomar (volta para a fila de prontos)"),
                                            ("encerrar", "Encerrar (remove do escalonamento)"),
                                            ("restante", "Definir tempo restante da ocorrência:"))):
            ttk.Radiobutton(self.corpo, text=texto, value=valor, variable=self.acao).grid(
                row=2 + i, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Spinbox(self.corpo, from_=1, to=100000, textvariable=self.rest, width=7).grid(
            row=5, column=2, sticky="w")
        self.tid.trace_add("write", lambda *_: self._atualizar_info())
        self._atualizar_info()

        self.mostrar()

    def _atualizar_info(self):
        """sugere no campo 'tempo restante' o valor atual da tarefa escolhida."""
        tc = self.sim.estado.tarefas.get(self.tid.get())
        if tc:
            self.rest.set(str(max(tc.restante, 1)))
            self.info.set(f"Estado atual: {tc.estado.value} · restante: {tc.restante} · "
                          f"CPU: {tc.cpu or '-'}")

    def aplicar(self):
        """Pede a mudança de estado ao simulador, que valida a ação."""
        a, t = self.acao.get(), self.tid.get()
        if a == "suspender":
            self.sim.suspender(t)
        elif a == "retomar":
            self.sim.retomar(t)
        elif a == "encerrar":
            self.sim.encerrar_tarefa(t)
        else:
            self.sim.definir_restante(t, self.rest.get())
