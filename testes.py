"""Testes do parser, escalonamento, edição e Gantt."""

import contextlib
import glob
import io
import os
import random
import tempfile
import unittest
import xml.etree.ElementTree as ET

import config
import escalonadores
import gantt
import main
from modelo import ErroEdicao, Estado, TipoEvento
from simulador import Simulador

PASTA = os.path.dirname(os.path.abspath(__file__))


def novo(texto: str, semente: int = 1) -> Simulador:
    """Cria um simulador a partir de uma configuração escrita no próprio teste."""
    return Simulador(config.carregar_texto(texto), semente=semente)


def eventos(sim, tipo, tarefa=None):
    """Filtra os eventos já registrados por tipo (e, opcionalmente, por tarefa)."""
    return [e for e in sim.eventos if e.tipo is tipo and (tarefa is None or e.tarefa == tarefa)]


class TestParser(unittest.TestCase):
    """Leitura do arquivo de configuração: formato flexível, avisos e erros claros."""

    def test_formato_flexivel(self):
        """Aceita espaços, linhas vazias, separador final e campos opcionais."""
        cfg = config.carregar_texto("\n  RM ; 3 ; 2 ;\n\n t1 ; ff0000 ;0;2;5;5;\nT2;#00FF00;1;1;4\n")
        self.assertEqual((cfg.algoritmo, cfg.quantum, cfg.n_cpus), ("RM", 3, 2))
        self.assertEqual([t.id for t in cfg.tarefas], ["t1", "T2"])
        self.assertEqual((cfg.tarefas[0].cor, cfg.tarefas[1].prazo), ("FF0000", 4))

    def test_algoritmo_sem_diferenciar_maiusculas(self):
        """'edf', 'Edf' e 'EDF' escolhem o mesmo algoritmo."""
        for nome in ("edf", "Edf", "EDF"):
            self.assertEqual(config.carregar_texto(f"{nome};1;1\nt;F00;0;1;2;2").algoritmo, "EDF")

    def test_aperiodica_ignorada_com_aviso(self):
        """Tarefa com período 0 é ignorada no Projeto A, com um aviso que explica o motivo."""
        cfg = config.carregar_texto("EDF;1;1\na;FF0000;0;1;0;1\nb;00FF00;0;1;3;3")
        self.assertEqual([t.id for t in cfg.tarefas], ["b"])
        self.assertTrue(any("aperiódica" in a for a in cfg.avisos))

    def test_todos_os_erros_sao_reportados(self):
        """Um arquivo com vários defeitos devolve todos os erros de uma vez, não só o primeiro."""
        with self.assertRaises(config.ErroConfig) as ctx:
            config.carregar_texto("XYZ;2;0\nt1;GG;a;0;-3;x\nt1;FF0000;0;1;3;3")
        texto = "\n".join(ctx.exception.erros)
        for trecho in ("algoritmo", "qtde_cpus", "cor 'GG'", "ingresso", "duracao",
                       "negativo", "prazo", "repetido"):
            self.assertIn(trecho, texto)

    def test_arquivo_inexistente_e_vazio(self):
        """Arquivo inexistente, vazio ou sem nenhuma tarefa é recusado com ErroConfig."""
        with self.assertRaises(config.ErroConfig):
            config.carregar_arquivo("/nao/existe.txt")
        with self.assertRaises(config.ErroConfig):
            config.carregar_texto("   \n\n")
        with self.assertRaises(config.ErroConfig):
            config.carregar_texto("EDF;1;1\n")

    def test_carrega_de_qualquer_caminho_e_codificacao(self):
        """O arquivo pode ter qualquer nome ou pasta e estar em UTF-8 ou cp1252 (Windows)."""
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "qualquer nome.dat")
            with open(caminho, "wb") as f:
                f.write("EDF;1;1\r\nação;FF0000;0;1;3;3\r\n".encode("cp1252"))
            self.assertEqual(config.carregar_arquivo(caminho).tarefas[0].id, "ação")


class TestAlgoritmos(unittest.TestCase):
    """RM e EDF em casos calculados à mão, multiprocessador e plugin de um algoritmo novo."""

    SET = "{};1;1\nt1;FF0000;0;2;5;5\nt2;00FF00;0;4;7;7\n"

    def test_rm_perde_prazo_calculado_a_mao(self):
        """Com RM, t2 perde o 1º prazo (t=7) e termina em t=8, como prevê a análise de resposta."""
        sim = novo(self.SET.format("RM"))
        sim.executar_ate_o_fim()
        perdidos = eventos(sim, TipoEvento.PRAZO_PERDIDO, "t2")
        self.assertEqual(perdidos[0].instante, 7)
        termino = [e for e in eventos(sim, TipoEvento.TERMINO, "t2")][0]
        self.assertEqual(termino.instante, 8)
        self.assertFalse(eventos(sim, TipoEvento.PRAZO_PERDIDO, "t1"))

    def test_edf_escalona_o_mesmo_conjunto(self):
        """O mesmo conjunto (U ≈ 0,97 < 1) não perde nenhum prazo com EDF."""
        sim = novo(self.SET.format("EDF"))
        sim.executar_ate_o_fim()
        self.assertFalse(eventos(sim, TipoEvento.PRAZO_PERDIDO))
        self.assertTrue(sim.terminou)

    def test_cada_tarefa_executa_exatamente_10_vezes(self):
        """cada tarefa periódica conclui exatamente 10 ocorrências e é encerrada."""
        sim = novo(self.SET.format("EDF"))
        sim.executar_ate_o_fim()
        for tc in sim.estado.tarefas.values():
            self.assertEqual(tc.concluidas, 10)
            self.assertEqual(tc.tempo_exec, 10 * tc.duracao)
            self.assertIs(tc.estado, Estado.ENCERRADA)

    def test_tarefa_que_perde_prazo_continua_executando(self):
        """perdendo todos os prazos (C > T), a tarefa ainda executa as 10 ocorrências."""
        sim = novo("EDF;1;1\nt1;FF0000;0;5;3;3\n")
        sim.executar_ate_o_fim()
        t = sim.estado.tarefas["t1"]
        self.assertEqual(t.concluidas, 10)
        self.assertEqual(t.perdas_prazo, 10)
        self.assertEqual(t.tempo_exec, 50)

    def test_multiprocessador_e_cpu_desligada(self):
        """Com 3 CPUs e 2 tarefas, a 3ª CPU fica desligada e o evento é registrado."""
        sim = novo("EDF;2;3\nt1;FF0000;0;2;10;10\nt2;00FF00;0;2;10;10\n")
        sim.passo()
        self.assertEqual(sim.trace[0].cpus, ("t1", "t2", None))
        self.assertFalse(sim.estado.cpus[2].ligada)
        self.assertTrue(eventos(sim, TipoEvento.CPU_DESLIGA))

    def test_plugin_de_novo_algoritmo(self):
        """um algoritmo novo entra por @escalonador sem alterar o simulador."""
        @escalonadores.escalonador("TESTE_MAIOR_C")
        def maior_duracao(cands, m, ctx):
            """Algoritmo de teste: a tarefa de maior duração tem a maior prioridade."""
            return ctx.selecionar(cands, m, lambda t: -t.duracao)
        sim = novo("TESTE_MAIOR_C;1;1\nt1;FF0000;0;1;4;4\nt2;00FF00;0;3;8;8\n")
        sim.passo()
        self.assertEqual(sim.trace[0].cpus, ("t2",))
        del escalonadores.REGISTRO["TESTE_MAIOR_C"]


class TestDesempate(unittest.TestCase):
    """Cenários separados para conferir cada um dos cinco desempates."""

    def test_criterio1_quem_executa_continua(self):
        """Critério 1: a tarefa que já executa não é preemptada por outra empatada em prioridade."""
        sim = novo("RM;1;1\nt1;FF0000;0;4;20;20\nt2;00FF00;1;4;20;10\n")
        sim.executar_ate_o_fim()
        self.assertFalse(eventos(sim, TipoEvento.PREEMPCAO))
        self.assertFalse(eventos(sim, TipoEvento.SORTEIO))

    def test_criterio2_menor_prazo_absoluto(self):
        """Critério 2: entre empatadas em prioridade, vence o menor prazo absoluto."""
        sim = novo("RM;1;1\nt1;FF0000;0;2;20;18\nt2;00FF00;0;3;20;9\n")
        sim.passo()
        self.assertEqual(sim.trace[0].cpus, ("t2",))

    def test_criterio3_quem_entrou_antes_na_fila(self):
        """Critério 3: persistindo o empate, vence quem entrou antes na fila de prontos."""
        sim = novo("EDF;1;1\nx;FF0000;0;8;100;9\na;00FF00;0;2;100;10\nb;0000FF;5;1;100;5\n")
        sim.executar_ate_o_fim()
        quem = [t.cpus[0] for t in sim.trace[:11]]
        self.assertEqual(quem, ["x"] * 8 + ["a", "a", "b"])
        self.assertFalse(eventos(sim, TipoEvento.SORTEIO))

    def test_criterio4_menor_duracao(self):
        """Critério 4: persistindo o empate, vence a tarefa de menor duração."""
        for semente in range(1, 7):
            sim = novo("RM;1;1\nt1;FF0000;0;5;20;20\nt2;00FF00;0;2;20;20\n", semente)
            sim.passo()
            self.assertEqual(sim.trace[0].cpus, ("t2",))
            self.assertFalse(eventos(sim, TipoEvento.SORTEIO))

    def test_criterio5_sorteio_reprodutivel(self):
        """Critério 5: sorteio de verdade (sementes diferentes, escolhas diferentes) e reprodutível."""
        txt = "RM;1;1\nt1;FF0000;0;2;20;20\nt2;00FF00;0;2;20;20\nt3;0000FF;0;2;20;20\n"
        a, b = novo(txt, semente=7), novo(txt, semente=7)
        a.executar_ate_o_fim()
        b.executar_ate_o_fim()
        self.assertTrue(eventos(a, TipoEvento.SORTEIO))
        self.assertEqual(a.trace, b.trace)
        primeiros = set()
        for semente in range(1, 21):
            sim = novo(txt, semente)
            sim.passo()
            primeiros.add(sim.trace[0].cpus[0])
        self.assertGreater(len(primeiros), 1)


class TestHistoricoEEdicao(unittest.TestCase):
    """Histórico (voltar/avançar) e modificações manuais."""

    TXT = "EDF;2;2\nt1;FF0000;0;2;5;5\nt2;00FF00;0;3;7;7\nt3;0000FF;1;2;10;8\n"

    def test_voltar_e_avancar_reproduzem_o_mesmo_estado(self):
        """Depois de um passeio aleatório no tempo, o trace e os eventos são exatamente os mesmos."""
        ref = novo(self.TXT)
        ref.executar_ate_o_fim()
        sim = novo(self.TXT)
        rnd = random.Random(3)
        for _ in range(200):
            (sim.voltar if rnd.random() < 0.35 else sim.passo)()
        sim.ir_para(ref.ultimo)
        self.assertEqual(sim.trace_visivel(), ref.trace)
        self.assertEqual(sim.eventos_visiveis(), ref.eventos)
        for t in (0, 3, 17, ref.ultimo):
            sim.ir_para(t)
            self.assertEqual(sim.relogio, t)

    def test_suspender_retomar_e_validacoes(self):
        """Suspender tira a tarefa da CPU, retomar a devolve, pedidos incoerentes são recusados."""
        sim = novo(self.TXT)
        sim.ir_para(1)
        self.assertEqual(sim.estado.cpus[0].tarefa_id, "t1")
        sim.suspender("t1")
        self.assertIs(sim.estado.tarefas["t1"].estado, Estado.SUSPENSA)
        self.assertNotIn("t1", [c.tarefa_id for c in sim.estado.cpus])
        with self.assertRaises(ErroEdicao):
            sim.suspender("t1")
        sim.passo()
        self.assertIn("t1", sim.trace[-1].suspensas)
        sim.retomar("t1")
        self.assertIs(sim.estado.tarefas["t1"].estado, Estado.EXECUTANDO)
        with self.assertRaises(ErroEdicao):
            sim.retomar("t1")
        with self.assertRaises(ErroEdicao):
            sim.suspender("inexistente")

    def test_editar_no_passado_descarta_o_futuro(self):
        """Modificar em t=4 apaga os passos seguintes, a simulação segue por uma nova linha do tempo."""
        sim = novo(self.TXT)
        sim.executar_ate_o_fim()
        sim.ir_para(4)
        sim.editar_tarefa("t2", duracao=1, cor="123456")
        self.assertEqual(sim.ultimo, 4)
        self.assertEqual(len(sim.trace), 4)
        self.assertEqual(sim.estado.tarefas["t2"].cor, "123456")
        self.assertEqual(sim.executar_ate_o_fim(), "terminou")

    def test_edicoes_invalidas_nao_alteram_nada(self):
        """Toda modificação inválida é recusada com ErroEdicao e não deixa rastro algum."""
        sim = novo(self.TXT)
        sim.ir_para(3)
        antes = (sim.ultimo, len(sim.eventos))
        for chamada in (lambda: sim.editar_tarefa("t1", duracao="x"),
                        lambda: sim.editar_tarefa("t1", ingresso=9),
                        lambda: sim.editar_tarefa("t1", periodo=0),
                        lambda: sim.editar_tarefa("t1", cor="ZZZ"),
                        lambda: sim.adicionar_tarefa("t1", duracao=1, periodo=3),
                        lambda: sim.adicionar_tarefa("t9", ingresso=1, periodo=3),
                        lambda: sim.definir_sistema(algoritmo="XYZ"),
                        lambda: sim.definir_sistema(n_cpus=0),
                        lambda: sim.definir_restante("t1", 0)):
            with self.assertRaises(ErroEdicao):
                chamada()
        self.assertEqual((sim.ultimo, len(sim.eventos)), antes)

    def test_adicionar_tarefa_e_mudar_sistema(self):
        """Cria tarefa e troca algoritmo, quantum e CPUs no meio da simulação, que ainda termina."""
        sim = novo(self.TXT)
        sim.ir_para(2)
        sim.adicionar_tarefa("t4", cor="ABCDEF", ingresso=2, duracao=1, periodo=4)
        self.assertIn("t4", sim.estado.tarefas)
        sim.definir_sistema(algoritmo="rm", quantum=3, n_cpus=1)
        self.assertEqual((sim.estado.algoritmo, sim.estado.quantum, len(sim.estado.cpus)),
                         ("RM", 3, 1))
        self.assertEqual(sim.executar_ate_o_fim(), "terminou")

    def test_todas_suspensas_trava_com_mensagem(self):
        """Se só restam tarefas suspensas, a simulação fica 'travada' em vez de rodar para sempre."""
        sim = novo("EDF;1;1\nt1;FF0000;0;2;5;5\n")
        sim.suspender("t1")
        self.assertTrue(sim.travada)
        self.assertEqual(sim.executar_ate_o_fim(), "travada")


class TestInvariantes(unittest.TestCase):
    """Propriedades que valem para QUALQUER conjunto de tarefas (testadas com 60 aleatórios)."""

    def test_propriedades_em_conjuntos_aleatorios(self):
        """Em 60 conjuntos aleatórios valem as invariantes do escalonador (veja os comentários)."""
        rnd = random.Random(2026)
        for caso in range(60):
            alg = rnd.choice(["RM", "EDF"])
            m = rnd.randint(1, 4)
            linhas = [f"{alg};{rnd.randint(0, 3)};{m}"]
            for i in range(rnd.randint(1, 6)):
                per = rnd.randint(2, 14)
                linhas.append(f"t{i + 1};{rnd.randrange(16**6):06X};{rnd.randint(0, 6)};"
                              f"{rnd.randint(1, per + 2)};{per};{rnd.randint(1, per + 3)}")
            sim = novo("\n".join(linhas), semente=caso)
            while sim.passo():
                e = sim.estado
                exec_ = [t for t in e.tarefas.values() if t.estado is Estado.EXECUTANDO]
                prontas = [t for t in e.tarefas.values() if t.estado is Estado.PRONTA]
                ids = [c.tarefa_id for c in e.cpus if c.tarefa_id]
                self.assertEqual(len(ids), len(set(ids)))
                self.assertEqual(sorted(ids), sorted(t.id for t in exec_))
                if prontas:
                    self.assertTrue(all(c.tarefa_id for c in e.cpus), linhas)
                for x in exec_:
                    for r in prontas:
                        if alg == "RM":
                            self.assertLessEqual(x.periodo, r.periodo, linhas)
                        else:
                            self.assertLessEqual(x.prazo_abs, r.prazo_abs, linhas)
            if sim.terminou:
                for tc in sim.estado.tarefas.values():
                    self.assertEqual(tc.concluidas, 10)
                    self.assertEqual(tc.tempo_exec, 10 * tc.duracao)


class TestGantt(unittest.TestCase):
    """Imagem final do Gantt."""

    def test_svg_valido_com_legenda_e_sem_limite_de_tempo(self):
        """O SVG é XML bem formado, traz legenda, tarefas, CPUs e 'desligada', e cresce com o tempo."""
        sim = novo("EDF;2;2\nt01;E6194B;0;2;5;5\nt02;3CB44B;0;3;7;7\n")
        sim.executar_ate_o_fim()
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "g.svg")
            gantt.exportar_svg(sim, caminho)
            raiz = ET.parse(caminho).getroot()
            with open(caminho, encoding="utf-8") as f:
                texto = f.read()
        for trecho in ("Legenda", "t01", "t02", "CPU 1", "CPU 2", "desligada"):
            self.assertIn(trecho, texto)
        self.assertGreater(float(raiz.get("width")), sim.relogio * 10)


class TestLinhaDeComando(unittest.TestCase):
    """main.py --completo: o mesmo caminho que o `make completo` e os exemplos entregues."""

    @classmethod
    def setUpClass(cls):
        """Gera os exemplos em uma pasta temporária, sem depender de arquivos externos."""
        from exemplos import gerar
        cls.pasta_exemplos = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.pasta_exemplos.cleanup)
        cls.exemplos = str(gerar(cls.pasta_exemplos.name))

    def rodar(self, *argv):
        """Executa o comando e captura o código de saída, o resultado e os erros."""
        saida, erro = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
            codigo = main.main(list(argv))
        return codigo, saida.getvalue(), erro.getvalue()

    def test_exemplos_entregues_rodam_e_geram_svg(self):
        """Os 4 exemplos válidos entregues rodam até o fim (código 0) e geram SVG bem formado."""
        with tempfile.TemporaryDirectory() as pasta:
            for nome in ("exemplo_edf_2cpus", "exemplo_rm_perde_prazo", "exemplo_desempate",
                         "exemplo_avisos"):
                svg = os.path.join(pasta, nome + ".svg")
                codigo, saida, erro = self.rodar(os.path.join(self.exemplos, nome + ".txt"),
                                                 "--completo", "--saida", svg)
                self.assertEqual(codigo, main.SAIDA_OK, (nome, saida, erro))
                self.assertTrue(os.path.getsize(svg) > 1000, nome)
                ET.parse(svg)

    def test_rm_do_exemplo_perde_prazos_e_edf_nao(self):
        """No exemplo de RM com 2 prazos perdidos, trocar o algoritmo para EDF elimina as perdas."""
        arq = os.path.join(self.exemplos, "exemplo_rm_perde_prazo.txt")
        with tempfile.TemporaryDirectory() as pasta:
            _, saida, _ = self.rodar(arq, "--completo", "--saida", os.path.join(pasta, "a.svg"))
        self.assertIn("Prazos perdidos: 2", saida)
        texto = config.ler_texto(arq).replace("RM;2;1", "EDF;2;1")
        sim = novo(texto)
        sim.executar_ate_o_fim()
        self.assertEqual(sum(t.perdas_prazo for t in sim.estado.tarefas.values()), 0)

    def test_arquivo_com_erros_devolve_codigo_2_e_lista_todos(self):
        """Arquivo com erros: código de saída 2 e uma linha 'Linha n' para cada erro."""
        codigo, _, erro = self.rodar(os.path.join(self.exemplos, "exemplo_erros.txt"), "--completo")
        self.assertEqual(codigo, main.SAIDA_CONFIG)
        self.assertGreaterEqual(erro.count("Linha "), 6)

    def test_sem_arquivo_e_arquivo_inexistente(self):
        """Sem arquivo: código 1 (uso), arquivo inexistente: código 2 ('não encontrado')."""
        self.assertEqual(self.rodar("--completo")[0], main.SAIDA_USO)
        codigo, _, erro = self.rodar("nao_existe.txt", "--completo")
        self.assertEqual(codigo, main.SAIDA_CONFIG)
        self.assertIn("não encontrado", erro)

    def test_mesma_semente_mesmo_resultado(self):
        """Mesma semente, mesmo resultado (sorteios incluídos), outra semente muda os sorteios."""
        arq = os.path.join(self.exemplos, "exemplo_desempate.txt")
        with tempfile.TemporaryDirectory() as pasta:
            a = self.rodar(arq, "--completo", "--eventos", "--saida", os.path.join(pasta, "a.svg"))[1]
            b = self.rodar(arq, "--completo", "--eventos", "--saida", os.path.join(pasta, "b.svg"))[1]
            c = self.rodar(arq, "--completo", "--eventos", "--semente", "7",
                           "--saida", os.path.join(pasta, "c.svg"))[1]
        corpo = lambda s: s.split("Imagem do Gantt")[0]
        self.assertEqual(corpo(a), corpo(b))
        self.assertNotEqual(corpo(a), corpo(c))

    def test_exemplo_e_aviso_de_servidor(self):
        """--exemplo imprime uma configuração válida, ids BSxx geram o aviso de servidor (Projeto B)."""
        _, saida, _ = self.rodar("--exemplo")
        cfg = config.carregar_texto(saida)
        self.assertEqual((cfg.algoritmo, cfg.n_cpus, len(cfg.tarefas)), ("EDF", 2, 3))
        aviso = config.carregar_texto("RM;1;1\nBS01;FF0000;0;1;4;4\nt1;00FF00;0;1;5;5").avisos
        self.assertTrue(any("servidor" in a and "BS01" in a for a in aviso), aviso)

    def test_quantum_zero_e_aceito(self):
        """Quantum 0 (sem fatiamento de tempo) é aceito e a simulação termina."""
        sim = novo("EDF;0;1\nt1;FF0000;0;1;4;4")
        sim.executar_ate_o_fim()
        self.assertTrue(sim.terminou)


if __name__ == "__main__":
    unittest.main(verbosity=2)
