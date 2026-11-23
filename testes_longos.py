"""Verificação de simulações com horizonte longo."""

import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

import config
import gantt
from simulador import Simulador


class HorizonteLongo(unittest.TestCase):
    """Confere uma simulação completa de 270.001 ticks e a imagem gerada."""

    def test_simulacao_e_imagem_completas(self):
        s = Simulador(config.carregar_texto('EDF;1;1\na;FF0000;0;1;30000;30000'))
        self.assertEqual(s.executar_ate_o_fim(), 'terminou')
        self.assertEqual(s.relogio, 270001)
        self.assertEqual(s.estado.tarefas['a'].concluidas, 10)

        s.voltar()
        self.assertEqual(s.relogio, 270000)
        s.passo()
        self.assertTrue(s.terminou)

        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / 'longo.svg'
            gantt.exportar_svg(s, str(caminho))
            raiz = ET.parse(caminho).getroot()
            self.assertGreater(int(raiz.get('width')), s.relogio * 10)
            self.assertIn('270001', caminho.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
