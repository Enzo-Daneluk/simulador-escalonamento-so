"""Interface gráfica do simulador."""

from __future__ import annotations

import os
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import config
import escalonadores
import gantt
from dialogos import DialogoEstado, DialogoSistema, DialogoTarefa
from modelo import ErroEdicao, Estado, TipoEvento, chave_natural
from simulador import ErroEscalonador, Simulador


def clarear(cor_hex: str, f: float = 0.8) -> str:
    """Mistura a cor com branco (fundo suave das linhas da tabela de tarefas)."""
    r, g, b = (int(cor_hex[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02X%02X%02X" % tuple(int(c + (255 - c) * f) for c in (r, g, b))


class Aplicacao:
    """Janela principal e controles da simulação."""

    COLUNAS_TAREFAS = (("id", "Tarefa", 60), ("estado", "Estado", 190), ("cpu", "CPU", 40),
                       ("restante", "Restante", 62), ("prazo", "Prazo abs.", 70),
                       ("prox", "Próx. ativação", 90), ("ativ", "Ativações", 74),
                       ("conc", "Concluídas", 84), ("perdas", "Prazos perdidos", 116),
                       ("preemp", "Preempções", 92), ("migr", "Migrações", 84))

    def __init__(self, caminho=None, perguntar_arquivo=True, semente=2026):
        """Monta a janela e abre a configuração recebida, se houver."""
        self.raiz = tk.Tk()
        self.raiz.title("Simulador de SO multitarefa de tempo compartilhado — Projeto A (RM / EDF)")
        self.raiz.geometry("1340x880")
        self.raiz.minsize(900, 600)

        self.semente = semente
        self.sim = None
        self.completo = False
        self.job_completo = None
        self.caminho = None
        self.escala = 26.0
        self.auto = False
        self.job = None
        self.sel_id = None
        self.exportado_em = None
        self.largura_legenda = 0

        self._montar_menu()
        self._montar_barra()
        self._montar_corpo()

        self.var_status = tk.StringVar(value="Abra um arquivo de configuração (Arquivo ▸ Abrir).")
        self.lbl_status = tk.Label(self.raiz, textvariable=self.var_status, anchor="w", padx=8,
                                   relief="sunken", bg="#F3F3F3")
        self.lbl_status.pack(side="bottom", fill="x")

        self.raiz.protocol("WM_DELETE_WINDOW", self._fechar)
        for tecla, f in (("<Right>", self.passo), ("<Left>", self.voltar),
                         ("<space>", self.alternar_auto), ("<Control-o>", self.abrir),
                         ("<Control-e>", self.exportar)):
            self.raiz.bind(tecla, lambda _e, f=f: f())

        self._atualizar()
        if caminho:
            self.carregar(caminho)
        elif perguntar_arquivo:
            self.raiz.after(250, self.abrir)

    # Montagem da janela.

    def _montar_menu(self):
        """menus Arquivo, Simulação, Editar e Ajuda."""
        m = tk.Menu(self.raiz)

        arq = tk.Menu(m, tearoff=0)
        arq.add_command(label="Abrir configuração…   Ctrl+O", command=self.abrir)
        arq.add_command(label="Exportar Gantt (SVG)…   Ctrl+E", command=self.exportar)
        arq.add_command(label="Carregar escalonador externo (.py)…", command=self.carregar_plugin)
        arq.add_separator()
        arq.add_command(label="Sair", command=self._fechar)

        sim = tk.Menu(m, tearoff=0)
        sim.add_command(label="Passo →", command=self.passo)
        sim.add_command(label="Voltar ←", command=self.voltar)
        sim.add_command(label="Ir para o instante…", command=self.ir_para)
        sim.add_command(label="Auto (espaço)", command=self.alternar_auto)
        sim.add_command(label="Executar completo", command=self.executar_completo)
        sim.add_command(label="Reiniciar", command=self.reiniciar)

        ed = tk.Menu(m, tearoff=0)
        ed.add_command(label="Estado da tarefa…", command=self.dlg_estado)
        ed.add_command(label="Editar tarefa selecionada…", command=self.dlg_editar)
        ed.add_command(label="Adicionar tarefa…", command=self.dlg_adicionar)
        ed.add_command(label="Sistema (algoritmo, quantum, CPUs)…", command=self.dlg_sistema)

        aj = tk.Menu(m, tearoff=0)
        aj.add_command(label="Sobre o simulador", command=self.sobre)
        for nome, menu in (("Arquivo", arq), ("Simulação", sim), ("Editar", ed), ("Ajuda", aj)):
            m.add_cascade(label=nome, menu=menu)
        self.raiz.config(menu=m)

    def _montar_barra(self):
        """monta os botões, o controle de velocidade e o relógio."""
        barra = ttk.Frame(self.raiz, padding=(6, 4))
        barra.pack(side="top", fill="x")
        self.botoes = {}
        for chave, texto, cmd in (("abrir", "Abrir…", self.abrir), ("reiniciar", "Reiniciar", self.reiniciar),
                                  ("voltar", "◀ Voltar", self.voltar), ("passo", "Passo ▶", self.passo),
                                  ("auto", "Auto ▶▶", self.alternar_auto),
                                  ("completo", "Executar completo", self.executar_completo),
                                  ("exportar", "Exportar SVG", self.exportar)):
            b = ttk.Button(barra, text=texto, command=cmd)
            b.pack(side="left", padx=2)
            self.botoes[chave] = b
        ttk.Separator(barra, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Label(barra, text="Ir para t =").pack(side="left")
        self.var_ir = tk.StringVar(value="0")
        e = ttk.Entry(barra, textvariable=self.var_ir, width=6)
        e.pack(side="left", padx=2)
        e.bind("<Return>", lambda _e: self.ir_para(self.var_ir.get()))
        ttk.Button(barra, text="Ir", command=lambda: self.ir_para(self.var_ir.get())).pack(side="left")
        ttk.Separator(barra, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(barra, text="Zoom −", width=7, command=lambda: self.zoom(0.8)).pack(side="left", padx=1)
        ttk.Button(barra, text="Zoom +", width=7, command=lambda: self.zoom(1.25)).pack(side="left", padx=1)
        ttk.Label(barra, text="  Velocidade:").pack(side="left")
        self.var_vel = tk.IntVar(value=5)
        ttk.Scale(barra, from_=1, to=10, variable=self.var_vel, length=90).pack(side="left")

        info = ttk.Frame(self.raiz, padding=(10, 2))
        info.pack(side="top", fill="x")
        self.lbl_relogio = ttk.Label(info, text="t = 0", font=("Helvetica", 18, "bold"),
                                     foreground="#D50000")
        self.lbl_relogio.pack(side="left")
        self.var_sistema = tk.StringVar()
        ttk.Label(info, textvariable=self.var_sistema, font=("Helvetica", 11)).pack(side="left", padx=18)
        self.var_situacao = tk.StringVar()
        ttk.Label(info, textvariable=self.var_situacao, font=("Helvetica", 11, "bold")).pack(side="right")

    def _montar_corpo(self):
        """coloca o Gantt em cima e as abas de informações embaixo."""
        painel = ttk.PanedWindow(self.raiz, orient="vertical")
        painel.pack(side="top", fill="both", expand=True)
        topo = ttk.Frame(painel)
        painel.add(topo, weight=3)
        quadro = ttk.Frame(topo)
        quadro.pack(side="top", fill="both", expand=True)
        self.canvas = tk.Canvas(quadro, bg="white", highlightthickness=0)
        sx = ttk.Scrollbar(quadro, orient="horizontal", command=self.canvas.xview)
        sy = ttk.Scrollbar(quadro, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=lambda a, b: (sx.set(a, b), self._fixar_rotulos()),
                              yscrollcommand=sy.set)
        self._esq_rotulos = 0.0
        sx.pack(side="bottom", fill="x")
        sy.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.canvas_legenda = tk.Canvas(topo, height=122, bg="white", highlightthickness=1,
                                        highlightbackground="#CCCCCC")
        self.canvas_legenda.pack(side="bottom", fill="x")
        self.canvas_legenda.bind("<Configure>", self._redesenhar_legenda)

        self.abas = ttk.Notebook(painel)
        painel.add(self.abas, weight=2)
        aba = ttk.PanedWindow(self.abas, orient="horizontal")
        self.abas.add(aba, text="Tarefas (TCB)")
        self.tv = ttk.Treeview(aba, columns=[c[0] for c in self.COLUNAS_TAREFAS], show="headings",
                               height=7, selectmode="browse")
        for chave, titulo, larg in self.COLUNAS_TAREFAS:
            self.tv.heading(chave, text=titulo)
            self.tv.column(chave, width=larg, anchor="w" if chave in ("id", "estado") else "center",
                           stretch=(chave == "estado"), minwidth=120 if chave == "estado" else larg)
        self.tv.bind("<<TreeviewSelect>>", self._ao_selecionar)
        self.tv.bind("<Double-1>", lambda _e: self.dlg_editar())
        aba.add(self.tv, weight=3)
        self.txt_tcb = tk.Text(aba, width=46, height=8, font="TkFixedFont", state="disabled",
                               bg="#FBFBFB")
        aba.add(self.txt_tcb, weight=2)

        self.tv_cpu = ttk.Treeview(self.abas, columns=("cpu", "estado", "tarefa", "ocup", "deslig",
                                                       "uso", "trocas"), show="headings", height=6)
        for chave, titulo, larg in (("cpu", "CPU", 60), ("estado", "Estado", 190), ("tarefa", "Tarefa", 90),
                                    ("ocup", "Ticks ocupada", 110), ("deslig", "Ticks desligada", 120),
                                    ("uso", "Uso (%)", 80), ("trocas", "Trocas de contexto", 130)):
            self.tv_cpu.heading(chave, text=titulo)
            self.tv_cpu.column(chave, width=larg, anchor="center")
        self.abas.add(self.tv_cpu, text="Processadores")

        aba_ev = ttk.Frame(self.abas)
        self.abas.add(aba_ev, text="Eventos")
        self.var_so_atual = tk.BooleanVar(value=False)
        ttk.Checkbutton(aba_ev, text="mostrar só o instante atual", variable=self.var_so_atual,
                        command=self._preencher_eventos).pack(side="top", anchor="w")
        self.txt_ev = tk.Text(aba_ev, height=8, font="TkFixedFont", state="disabled", wrap="none")
        sb = ttk.Scrollbar(aba_ev, command=self.txt_ev.yview)
        self.txt_ev.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.txt_ev.pack(side="left", fill="both", expand=True)
        self.txt_ev.tag_configure("agora", background="#FFF3C4")
        self.txt_ev.tag_configure("perdido", foreground="#D32F2F")

        self.txt_resumo = tk.Text(self.abas, height=8, font="TkFixedFont", state="disabled")
        self.abas.add(self.txt_resumo, text="Resumo / estatísticas")

        self.txt_avisos = tk.Text(self.abas, height=8, state="disabled", wrap="word")
        self.abas.add(self.txt_avisos, text="Avisos")

    def status(self, texto: str, erro: bool = False):
        """Mostra uma mensagem na barra de status (vermelha se for erro)."""
        self.var_status.set(texto)
        self.lbl_status.configure(fg="#B00020" if erro else "#1B1B1B")

    def _erro(self, titulo: str, texto: str):
        """Mostra o motivo do erro na janela e um resumo na barra de status."""
        self.status(texto.strip().splitlines()[0][:200], erro=True)
        messagebox.showerror(titulo, texto, parent=self.raiz)

    def _requer_sim(self) -> bool:
        """confere se dá para executar a ação com a simulação atual."""
        if self.completo:
            self.status("a simulação ainda está rodando. Cancele antes de editar ou voltar.")
            return False
        if self.sim is None:
            self.status("abra uma configuração primeiro.", erro=True)
            return False
        return True

    def _texto(self, widget, conteudo: str):
        """troca o conteúdo de uma caixa de texto somente leitura."""
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("end", conteudo)
        widget.configure(state="disabled")

    # Arquivos de configuração e imagens.

    def abrir(self):
        """Abre o seletor para escolher uma configuração em qualquer pasta."""
        if self.completo:
            return
        caminho = filedialog.askopenfilename(
            parent=self.raiz, title="Abrir arquivo de configuração",
            filetypes=[("Configuração (texto)", "*.txt *.cfg *.csv *.dat *.conf"),
                       ("Todos os arquivos", "*.*")])
        if caminho:
            self.carregar(caminho)

    def carregar(self, caminho: str):
        """Lê e valida o arquivo."""
        try:
            cfg = config.carregar_arquivo(caminho)
        except config.ErroConfig as exc:
            relato = "\n".join(exc.erros + ["AVISO: " + a for a in exc.avisos])
            self._texto(self.txt_avisos, f"ERROS ao carregar '{caminho}':\n{relato}\n")
            resumo = "\n".join((exc.erros + exc.avisos)[:20]) + (f"\n… e mais {len(exc.erros) - 20} erro(s) "
                                                  f"(veja a aba Avisos)." if len(exc.erros) > 20 else "")
            self._erro("Erro no arquivo de configuração",
                       f"O arquivo '{os.path.basename(caminho)}' não foi carregado:\n\n{resumo}")
            return
        self.parar_auto()
        self.cfg, self.caminho = cfg, caminho
        self.sim = Simulador(cfg, self.semente)
        self.sel_id, self.exportado_em = None, None
        self._texto(self.txt_avisos, f"Arquivo: {caminho}\n\n" + (
            "\n".join("• " + a for a in cfg.avisos) if cfg.avisos else "Nenhum aviso."))
        self.status(f"Configuração carregada: {len(cfg.tarefas)} tarefa(s), {cfg.n_cpus} CPU(s), "
                    f"{cfg.algoritmo}. {len(cfg.avisos)} aviso(s).")
        self._atualizar()
        self.raiz.after_idle(self._verificar_fim)
        if cfg.avisos:
            messagebox.showwarning("Avisos ao carregar a configuração",
                                   "\n".join("• " + a for a in cfg.avisos[:15]), parent=self.raiz)

    def exportar(self):
        """Grava o Gantt até o instante atual em um SVG escolhido pelo usuário."""
        if not self._requer_sim():
            return
        padrao = gantt.caminho_saida_padrao(self.caminho)
        destino = filedialog.asksaveasfilename(
            parent=self.raiz, title="Exportar gráfico de Gantt", defaultextension=".svg",
            initialdir=os.path.dirname(padrao), initialfile=os.path.basename(padrao),
            filetypes=[("Imagem SVG", "*.svg")])
        if destino:
            try:
                gantt.exportar_svg(self.sim, destino)
            except OSError as exc:
                self._erro("Falha ao exportar", f"Não foi possível gravar '{destino}': {exc.strerror}")
                return
            self.status(f"Gantt exportado até t={self.sim.relogio}: {destino}")

    def _exportar_final(self, avisar: bool = True):
        """Salva o SVG completo quando a simulação termina."""
        s = self.sim
        destino = gantt.caminho_saida_padrao(self.caminho)
        try:
            try:
                gantt.exportar_svg(s, destino)
            except OSError:
                destino = os.path.join(os.getcwd(), os.path.basename(destino))
                gantt.exportar_svg(s, destino)
        except OSError as exc:
            self._erro("Falha ao gerar a imagem final", f"Não foi possível gravar a imagem: {exc.strerror}")
            return
        self.exportado_em = s.ultimo
        perdas = sum(t.perdas_prazo for t in s.estado.tarefas.values())
        self.status(f"Simulação concluída em t={s.relogio}. Imagem do Gantt gerada: {destino}")
        if avisar:
            messagebox.showinfo("Simulação concluída",
                                f"Todas as tarefas terminaram em t = {s.relogio}.\n"
                                f"Prazos perdidos no total: {perdas}.\n\n"
                                f"Imagem do Gantt gerada em:\n{destino}", parent=self.raiz)

    def carregar_plugin(self):
        """Carrega um .py com novos algoritmos de escalonamento."""
        caminho = filedialog.askopenfilename(parent=self.raiz, title="Escalonador externo (.py)",
                                             filetypes=[("Python", "*.py")])
        if not caminho:
            return
        try:
            novos = escalonadores.carregar_plugin(caminho)
        except Exception as exc:
            self._erro("Falha ao carregar o escalonador", f"{type(exc).__name__}: {exc}")
            return
        self.status("Algoritmos carregados: " + (", ".join(novos) if novos else "nenhum novo") +
                    ". Use Editar ▸ Sistema para selecioná-los.")

    # Controles de execução e navegação.

    def passo(self):
        """Avança ou revisita um tick e atualiza a tela."""
        if not self._requer_sim():
            return
        try:
            avancou = self.sim.passo()
        except ErroEscalonador as exc:
            self.parar_auto()
            self._erro("Erro no escalonador", str(exc))
            return
        if not avancou:
            self.parar_auto()
            if self.sim.travada:
                self.status("a simulação está esperando, todas as tarefas restantes estão suspensas. "
                            "Use Editar ▸ Estado da tarefa para retomar alguma.", erro=True)
            else:
                self.status("a simulação já terminou, não há mais tarefas para executar.")
        else:
            self.status(f"Passo executado: t = {self.sim.relogio}.")
        self._atualizar()
        self._verificar_fim()

    def _verificar_fim(self):
        """se a simulação chegou ao fim, para o modo automático e gera a imagem final."""
        s = self.sim
        if s.terminou and s.cursor == s.ultimo and self.exportado_em != s.ultimo:
            self.parar_auto()
            self._exportar_final()

    def voltar(self):
        """Retrocede um passo no histórico, o relógio volta junto."""
        if not self._requer_sim():
            return
        if self.sim.voltar():
            self.status(f"Voltou para t = {self.sim.relogio}.")
        else:
            self.status("já estamos no tick 0, não dá para voltar mais.", erro=True)
        self._atualizar()

    def ir_para(self, valor=None):
        """Usa o histórico para voltar ou calcula os passos que ainda faltam."""
        if not self._requer_sim():
            return
        if valor is None:
            valor = simpledialog.askinteger("Ir para o instante", "Instante t:", parent=self.raiz,
                                            minvalue=0, initialvalue=self.sim.relogio)
            if valor is None:
                return
        try:
            alvo = int(str(valor).strip())
            if alvo < 0:
                raise ValueError
        except ValueError:
            self.status(f"Instante inválido: '{valor}'. Informe um inteiro ≥ 0.", erro=True)
            return
        try:
            atingido = self.sim.ir_para(alvo)
        except ErroEscalonador as exc:
            self._erro("Erro no escalonador", str(exc))
            return
        self.status(f"Foi para t = {atingido}" + ("" if atingido == alvo else
                    f" (a simulação parou aqui, pedido: {alvo})."))
        self._atualizar()
        self._verificar_fim()

    def reiniciar(self):
        """Volta a t = 0 com a configuração original, descartando as edições."""
        if self._requer_sim():
            self.parar_auto()
            self.sim.reiniciar()
            self.exportado_em = None
            self.status("voltamos ao tick 0 com a configuração original.")
            self._atualizar()

    def executar_completo(self):
        """Calcula em lotes para a janela continuar respondendo."""
        if self.completo:
            self._parar_completo()
            self._atualizar()
            self.status("execução parada. O histórico continua disponível.")
            return
        if not self._requer_sim():
            return
        self.parar_auto()
        self.completo = True
        for chave, botao in self.botoes.items():
            botao.state(["!disabled"] if chave == "completo" else ["disabled"])
        self.botoes["completo"].configure(text="Cancelar execução")
        self._lote_completo()

    def _parar_completo(self):
        """cancela apenas o agendamento, não elimina dados simulados."""
        self.completo = False
        if self.job_completo is not None:
            self.raiz.after_cancel(self.job_completo)
            self.job_completo = None
        self.botoes["completo"].configure(text="Executar completo")

    def _lote_completo(self):
        """devolve o controle ao Tk entre lotes para permitir cancelamento."""
        self.job_completo = None
        if not self.completo:
            return
        fim_lote = time.monotonic() + 0.035
        try:
            while not self.sim.terminou and not self.sim.travada:
                self.sim.passo()
                if time.monotonic() >= fim_lote:
                    self.status(f"Executando: {self.sim.relogio} ticks calculados…")
                    self.job_completo = self.raiz.after(1, self._lote_completo)
                    return
        except (ErroEscalonador, MemoryError) as exc:
            self._parar_completo()
            self._erro("Não foi possível continuar", str(exc) or "Memória insuficiente para manter o histórico.")
            return
        self._parar_completo()
        self._atualizar()
        if self.sim.terminou:
            self._exportar_final()
        else:
            self.status("só restaram tarefas suspensas. Retome uma delas ou avance um passo.", erro=True)

    def alternar_auto(self):
        """Liga ou pausa o avanço automático na velocidade escolhida."""
        if not self._requer_sim():
            return
        if self.auto:
            self.parar_auto()
            return
        self.auto = True
        self.botoes["auto"].configure(text="Pausar ⏸")
        self._auto_passo()

    def _auto_passo(self):
        """um passo do modo automático, agenda o próximo."""
        if not self.auto:
            return
        self.passo()
        if self.auto:
            self.job = self.raiz.after(1100 - 100 * int(self.var_vel.get()), self._auto_passo)

    def parar_auto(self):
        """Desliga o modo automático e cancela o próximo agendamento."""
        self.auto = False
        if self.job:
            self.raiz.after_cancel(self.job)
            self.job = None
        self.botoes["auto"].configure(text="Auto ▶▶")

    def zoom(self, fator: float):
        """Ajusta o zoom da tela. A exportação calcula sua própria escala."""
        self.escala = min(90.0, max(4.0, self.escala * fator))
        if self.sim and not self.completo:
            self._desenhar_gantt()

    # Edição durante a simulação.

    def _pronto_para_editar(self) -> bool:
        """avisa antes de descartar o futuro se a edição for no passado."""
        if not self._requer_sim():
            return False
        s = self.sim
        self.parar_auto()
        if s.cursor < s.ultimo:
            return messagebox.askokcancel(
                "Modificar no passado",
                f"Você está em t = {s.relogio}, mas a simulação já foi até t = {s.ultimo}.\n\n"
                f"Modificar aqui DESCARTA os passos seguintes e continua por uma nova linha do "
                f"tempo. Deseja continuar?", parent=self.raiz)
        return True

    def _apos_edicao(self):
        """atualiza a tela depois de uma modificação aceita."""
        self.exportado_em = None
        self.status(f"Modificação aplicada em t = {self.sim.relogio}, o futuro foi recalculado "
                    f"a partir daqui.")
        self._atualizar()
        self.raiz.after_idle(self._verificar_fim)

    def dlg_sistema(self):
        """Abre o diálogo que muda algoritmo, quantum e nº de CPUs."""
        if self._pronto_para_editar():
            DialogoSistema(self.raiz, self.sim, self._apos_edicao)

    def dlg_estado(self):
        """Abre as opções de estado e tempo restante da tarefa selecionada."""
        if self._pronto_para_editar():
            DialogoEstado(self.raiz, self.sim, self._apos_edicao, self.sel_id)

    def dlg_adicionar(self):
        """Abre o diálogo para criar uma nova tarefa durante a simulação."""
        if self._pronto_para_editar():
            DialogoTarefa(self.raiz, self.sim, self._apos_edicao)

    def dlg_editar(self):
        """Abre o diálogo para editar as características da tarefa selecionada."""
        if not self._requer_sim():
            return
        tc = self.sim.estado.tarefas.get(self.sel_id)
        if tc is None:
            self.status("escolha uma tarefa na tabela antes de editar.", erro=True)
            return
        if self._pronto_para_editar():
            DialogoTarefa(self.raiz, self.sim, self._apos_edicao, tarefa=tc)

    def sobre(self):
        """Janela 'Sobre'."""
        messagebox.showinfo(
            "Sobre", "Simulador de SO multitarefa preemptivo de tempo compartilhado\n"
            "Projeto A — escalonamento de tempo real (RM e EDF) em múltiplos processadores.\n\n"
            "Atalhos: → passo · ← voltar · espaço auto · Ctrl+O abrir · Ctrl+E exportar.", parent=self.raiz)

    # Atualização do gráfico e das informações das abas.

    def _atualizar(self):
        """Atualiza os controles, o gráfico e as abas conforme o passo atual."""
        s = self.sim
        if self.completo:
            return
        for chave, b in self.botoes.items():
            if chave != "abrir":
                b.state(["!disabled"] if s else ["disabled"])
        if s is None:
            self.canvas.delete("gantt")
            self.canvas.create_text(30, 40, anchor="w", tags="gantt", fill="#666666",
                                    font=("Helvetica", 14), text="Nenhuma simulação carregada.\n"
                                    "Use Arquivo ▸ Abrir para escolher um arquivo de configuração.")
            self.lbl_relogio.configure(text="t = –")
            return
        e = s.estado
        self.lbl_relogio.configure(text=f"t = {s.relogio}")
        self.var_sistema.set(f"Algoritmo: {e.algoritmo}    Quantum: {e.quantum}    CPUs: {len(e.cpus)}"
                             f"    Passo {s.cursor} de {s.ultimo}")
        self.var_situacao.set("FINALIZADA" if s.terminou else "TRAVADA" if s.travada else "em andamento")
        self.var_ir.set(str(s.relogio))
        self._desenhar_gantt()
        self._preencher_tarefas()
        self._preencher_cpus()
        self._preencher_eventos()
        self._preencher_resumo()
        self._redesenhar_legenda(forcar=True)

    def _desenhar_gantt(self):
        """Redesenha o Gantt com o relógio atual e mantém os rótulos visíveis."""
        s = self.sim
        self.canvas.delete("gantt")
        est = gantt.Estilo(escala=self.escala)
        v = gantt.vista_de(s, com_agora=True)
        d = gantt.construir(v, est)
        gantt.desenhar_tk(self.canvas, d)
        self.canvas.tag_raise("rotulo")
        self._esq_rotulos = 0.0
        self.canvas.configure(scrollregion=(0, 0, d.largura, d.altura))
        self.canvas.update_idletasks()
        x = est.margem_esq + v.agora * est.escala
        esq = self.canvas.canvasx(0)
        w = max(self.canvas.winfo_width(), 100)
        if x > esq + w - 50 or x < esq + 20:
            self.canvas.xview_moveto(max(0.0, (x - w * 0.8) / max(d.largura, 1)))

    def _fixar_rotulos(self):
        """Mantém os rótulos à esquerda quando o gráfico rola na horizontal."""
        esq = self.canvas.canvasx(0)
        if esq != self._esq_rotulos:
            self.canvas.move("rotulo", esq - self._esq_rotulos, 0)
            self._esq_rotulos = esq
            self.canvas.tag_raise("rotulo")

    def _redesenhar_legenda(self, _evento=None, forcar: bool = False):
        """Reorganiza as colunas da legenda quando a largura muda."""
        w = self.canvas_legenda.winfo_width()
        if w < 60 or (w == self.largura_legenda and not forcar):
            return
        self.largura_legenda = w
        self.canvas_legenda.delete("gantt")
        d = gantt.construir_legenda(w)
        gantt.desenhar_tk(self.canvas_legenda, d)
        self.canvas_legenda.configure(height=d.altura)

    def _preencher_tarefas(self):
        """tabela das tarefas (estado atual do TCB), preservando a seleção."""
        s = self.sim
        self.tv.delete(*self.tv.get_children())
        self.iid_para_id = {}
        for i, tc in enumerate(sorted(s.estado.tarefas.values(), key=lambda t: chave_natural(t.id))):
            iid = f"i{i}"
            self.iid_para_id[iid] = tc.id
            self.tv.tag_configure(iid, background=clarear(tc.cor))
            estado = tc.estado.value + (" (acumulada)" if len(
                [o for o in tc.ocorrencias if o.fim is None]) > 1 else "")
            self.tv.insert("", "end", iid=iid, tags=(iid,), values=(
                tc.id, estado, tc.cpu or "–", tc.restante if tc.atual else "–",
                tc.prazo_abs if tc.atual else "–",
                tc.proxima_ativacao if tc.proxima_ativacao is not None else "–",
                f"{tc.ativacoes}/10", tc.concluidas, tc.perdas_prazo, tc.preempcoes, tc.migracoes))
            if tc.id == self.sel_id:
                self.tv.selection_set(iid)
        self._mostrar_tcb()

    def _ao_selecionar(self, _e=None):
        """guarda a tarefa selecionada e mostra o TCB dela."""
        sel = self.tv.selection()
        if sel:
            self.sel_id = self.iid_para_id.get(sel[0])
            self._mostrar_tcb()

    def _mostrar_tcb(self):
        """Mostra os dados e as ocorrências da tarefa selecionada."""
        tc = self.sim.estado.tarefas.get(self.sel_id) if self.sim else None
        if tc is None:
            self._texto(self.txt_tcb, "Selecione uma tarefa na tabela\npara ver o TCB completo.\n"
                        "(duplo clique = editar)")
            return
        o = tc.atual
        abertas = [x for x in tc.ocorrencias if x.fim is None]
        L = [f"TCB de {tc.id}", "-" * 44,
             f"cor: {tc.cor}   ingresso: {tc.ingresso}",
             f"duração C: {tc.duracao}   período T: {tc.periodo}   prazo D: {tc.prazo}",
             f"lista_eventos: {';'.join(tc.eventos) or '—'}",
             f"estado: {tc.estado.value}",
             f"CPU atual: {tc.cpu or '—'}   última CPU: {tc.ultima_cpu or '—'}"]
        if o:
            L += [f"ocorrência atual: ativada em {o.ativacao}",
                  f"  prazo absoluto: {o.prazo_abs}   restante: {o.restante}",
                  f"  iniciou em: {o.inicio if o.inicio is not None else '—'}",
                  f"ocorrências acumuladas esperando: {len(abertas) - 1}"]
        else:
            L.append("ocorrência atual: nenhuma")
        L += [f"ativações: {tc.ativacoes}   concluídas: {tc.concluidas}",
              f"próxima ativação: {tc.proxima_ativacao if tc.proxima_ativacao is not None else '—'}",
              f"quantum restante: {tc.quantum_restante}",
              f"executou: {tc.tempo_exec}   esperou na fila: {tc.tempo_espera}",
              f"resposta máx.: {tc.resposta_max}   prazos perdidos: {tc.perdas_prazo}"]
        L.append("Ocorrências: ativação / prazo / duração / restante / fim")
        for job in tc.ocorrencias:
            fim = "cancelada" if job.cancelada else job.fim
            L.append(f"  {job.ativacao} / {job.prazo_abs} / {job.duracao} / {job.restante} / {fim}")
        self._texto(self.txt_tcb, "\n".join(L))

    def _preencher_cpus(self):
        """Mostra a tarefa atual e os totais de uso de cada CPU."""
        s = self.sim
        self.tv_cpu.delete(*self.tv_cpu.get_children())
        for c, est in zip(s.estado.cpus, s.estatisticas()["cpus"]):
            situacao = ("ligada" if c.ligada else "DESLIGADA") + f" desde t={c.desde}"
            self.tv_cpu.insert("", "end", values=(c.indice, situacao, c.tarefa_id or "—",
                                                  est["ocupada"], est["desligada"],
                                                  f"{est['uso']:.1f}", est["trocas"]))

    def _preencher_eventos(self):
        """aba Eventos: log textual de tudo o que aconteceu até o ponto atual."""
        s = self.sim
        if s is None:
            return
        evs = s.eventos_visiveis()
        if self.var_so_atual.get():
            evs = [e for e in evs if e.instante == s.relogio]
        extra = max(0, len(evs) - 800)
        evs = evs[-800:]
        w = self.txt_ev
        w.configure(state="normal")
        w.delete("1.0", "end")
        if extra:
            w.insert("end", f"… ({extra} eventos anteriores omitidos)\n")
        for e in evs:
            tags = (("agora",) if e.instante == s.relogio else ()) + (
                ("perdido",) if e.tipo is TipoEvento.PRAZO_PERDIDO else ())
            w.insert("end", f"t={e.instante:<5} {e.tipo.value:<42} {e.texto}\n", tags)
        w.configure(state="disabled")
        w.see("end")

    def _preencher_resumo(self):
        """aba Resumo: estatísticas por tarefa e por CPU."""
        s = self.sim
        est = s.estatisticas()
        L = [f"{'Tarefa':<8}{'Ativ':>5}{'Concl':>6}{'Perdas':>7}{'Preemp':>7}{'Migr':>5}{'Exec':>6}"
             f"{'Espera':>7}{'RespMáx':>8}{'RespMéd':>8}"]
        for t in est["tarefas"]:
            L.append(f"{t['id']:<8}{t['ativacoes']:>5}{t['concluidas']:>6}{t['perdas']:>7}"
                     f"{t['preempcoes']:>7}{t['migracoes']:>5}{t['exec']:>6}{t['espera']:>7}"
                     f"{t['resp_max']:>8}{t['resp_media']:>8.2f}")
        L += ["", f"{'CPU':<8}{'Ocupada':>8}{'Desligada':>10}{'Uso %':>8}{'Trocas':>8}"]
        for c in est["cpus"]:
            L.append(f"{c['indice']:<8}{c['ocupada']:>8}{c['desligada']:>10}{c['uso']:>8.1f}{c['trocas']:>8}")
        L += ["", f"Tempo simulado: {s.relogio} ticks   ·   situação: "
              f"{'finalizada' if s.terminou else 'em andamento'}"]
        self._texto(self.txt_resumo, "\n".join(L))

    def _fechar(self):
        """fecha a janela parando antes o modo automático."""
        self.parar_auto()
        self._parar_completo()
        self.raiz.destroy()

    def executar(self):
        """Entra no laço de eventos do Tkinter."""
        self.raiz.mainloop()
