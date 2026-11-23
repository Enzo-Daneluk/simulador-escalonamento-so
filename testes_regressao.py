"""Testes de regressão."""

import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

import config
import gantt
from modelo import ErroEdicao, Estado, TipoEvento, cor_padrao
from simulador import Simulador


def novo(tarefas, algoritmo='EDF', cpus=1):
    """Monta um cenário pequeno, com cabeçalho completo."""
    return Simulador(config.carregar_texto(f'{algoritmo};1;{cpus}\n{tarefas}'), semente=1)


class Regressao(unittest.TestCase):
    """Casos que conferem histórico, edição, prazos e exportação."""

    def test_ingresso_nao_e_ativacao(self):
        """A segunda ocorrência de a mantém a preferência pelo ingresso original."""
        s = novo('a;FF0000;0;1;10;10\nb;00FF00;5;1;100;15\nx;0000FF;5;7;100;8')
        s.ir_para(13)
        self.assertEqual(s.trace[12].cpus, ('a',))

    def test_editar_prazo_nao_reescreve_ocorrencias(self):
        """Prazo novo vale para a próxima ativação, nunca para o passado."""
        s = novo('a;FF0000;0;3;20;10')
        s.ir_para(3)
        s.editar_tarefa('a', prazo=1)
        self.assertEqual(s.estado.tarefas['a'].ocorrencias[0].prazo_abs, 10)
        self.assertFalse(any(e.tipo is TipoEvento.PRAZO for e in s.eventos))
        s.ir_para(21)
        self.assertEqual(s.estado.tarefas['a'].ocorrencias[1].prazo_abs, 21)
        self.assertEqual(s.estado.tarefas['a'].perdas_prazo, 1)

    def test_editar_periodo_preserva_proxima_ativacao(self):
        """A ocorrência já agendada permanece em 10, os próximos intervalos usam T=3."""
        s = novo('a;FF0000;0;1;10;10')
        s.ir_para(1)
        s.editar_tarefa('a', periodo=3)
        s.ir_para(13)
        self.assertEqual([o.ativacao for o in s.estado.tarefas['a'].ocorrencias], [0, 10, 13])

    def test_prazo_exato_e_historico(self):
        """Terminar no prazo vale. Voltar e avançar restaura o estado e os sorteios."""
        s = novo('a;FF0000;0;2;10;2')
        s.ir_para(2)
        antes = s.estado.clone()
        self.assertEqual(antes.tarefas['a'].perdas_prazo, 0)
        s.voltar()
        s.passo()
        self.assertEqual(s.estado, antes)

    def test_cores_unicas_arquivo_e_edicao(self):
        """Recusas de cores repetidas não descartam o futuro existente."""
        with self.assertRaises(config.ErroConfig):
            novo('a;FF0000;0;1;10;10\nb;ff0000;0;1;10;10')
        s = novo('a;FF0000;0;1;10;10\nb;00FF00;0;1;10;10')
        s.ir_para(5)
        s.voltar()
        antes = (s.estado.clone(), s.ultimo, list(s.eventos))
        with self.assertRaises(ErroEdicao):
            s.editar_tarefa('b', cor='FF0000')
        with self.assertRaises(ErroEdicao):
            s.adicionar_tarefa('c', cor='FF0000', ingresso=4)
        self.assertEqual((s.estado, s.ultimo, s.eventos), antes)

    def test_paleta_nao_limita_tarefas(self):
        """As primeiras cem sugestões são distintas."""
        usadas = set()
        for i in range(100):
            usadas.add(cor_padrao(i, usadas))
        self.assertEqual(len(usadas), 100)

    def test_ids_off_e_traco_no_gantt(self):
        """ID do usuário não é um código de energia do processador."""
        for tid in ('off', 'OFF', '-'):
            s = novo(f'{tid};FF0000;0;1;2;2')
            s.passo()
            d = gantt.construir(gantt.vista_de(s))
            dicas = [p.dica for p in d.prims if p.dica.startswith('CPU 1')]
            self.assertEqual(dicas, [f'CPU 1: {tid}, t=0 a t=1'])

    def test_eventos_simultaneos_no_mesmo_instante(self):
        """Os centros do dado e da ativação coincidem com x(0)."""
        s = novo('a;FF0000;0;1;20;20\nb;00FF00;0;1;20;20', 'RM')
        d = gantt.construir(gantt.vista_de(s))
        marcadores = [p for p in d.prims if p.dica.startswith('t=0:')]
        self.assertGreaterEqual(len(marcadores), 3)
        for p in marcadores:
            xs = p.pts[::2]
            self.assertAlmostEqual((min(xs) + max(xs)) / 2, gantt.Estilo().margem_esq)

    def test_suspensao_total_admite_passo_manual(self):
        """O completo pede intervenção, mas o relógio e os prazos continuam no manual."""
        s = novo('a;FF0000;0;2;5;1')
        s.suspender('a')
        self.assertEqual(s.executar_ate_o_fim(), 'travada')
        self.assertTrue(s.passo())
        self.assertEqual(s.relogio, 1)
        self.assertEqual(s.trace[0].suspensas, ('a',))
        self.assertEqual(s.estado.tarefas['a'].perdas_prazo, 1)

    def test_so_aperiodicas_carrega_vazio(self):
        """Ignorar todas as tarefas não transforma o arquivo em erro de conteúdo."""
        s = novo('a;FF0000;0;1;0;1')
        self.assertTrue(s.terminou)
        self.assertTrue(s.cfg.avisos)
        self.assertEqual(s.executar_ate_o_fim(), 'terminou')

    def test_carga_finita_pode_cumprir_prazos(self):
        """Mesmo com U > m, dez ocorrências podem cumprir prazos bem longos."""
        s = novo('a;FF0000;0;2;1;100')
        s.executar_ate_o_fim()
        self.assertEqual(s.estado.tarefas['a'].perdas_prazo, 0)
        self.assertFalse(any('inevitáveis' in a for a in s.cfg.avisos))

    def test_restante_ajusta_orcamento_da_ocorrencia(self):
        """Mudar o restante não altera a duração das próximas ocorrências."""
        s = novo('a;FF0000;0;3;10;10')
        s.passo()
        s.definir_restante('a', 5)
        o = s.estado.tarefas['a'].atual
        self.assertEqual((o.duracao, o.executado, o.restante), (6, 1, 5))
        self.assertEqual(s.estado.tarefas['a'].duracao, 3)

    def test_cancelamento_nao_inventa_conclusoes(self):
        """Cancelamento manual preserva o trabalho e as estatísticas reais."""
        s = novo('a;FF0000;0;3;10;10')
        s.passo()
        s.encerrar_tarefa('a')
        self.assertTrue(s.terminou)
        self.assertEqual(s.estado.tarefas['a'].concluidas, 0)
        self.assertTrue(s.estado.tarefas['a'].ocorrencias[0].cancelada)

    def test_modo_completo_apos_voltar(self):
        """Retomar do passado usa o histórico antes de prosseguir."""
        s = novo('a;FF0000;0;1;3;3')
        s.ir_para(5)
        s.voltar()
        self.assertEqual(s.executar_ate_o_fim(), 'terminou')
        self.assertEqual(s.estado.tarefas['a'].concluidas, 10)


if __name__ == '__main__':
    unittest.main(verbosity=2)
