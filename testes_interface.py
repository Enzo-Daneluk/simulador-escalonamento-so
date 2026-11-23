"""Testes de integração da interface."""

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from interface import Aplicacao
from modelo import Estado


class InterfaceReal(unittest.TestCase):
    """Exercita callbacks e widgets, sem automação de cliques ou arquivos fixos."""

    def test_autoteste_serializa_caminhos_tcl(self):
        """Tcl pode devolver Tcl_Obj em vez de str, especialmente no pacote."""
        import main
        import json
        with tempfile.TemporaryDirectory() as pasta:
            self.assertEqual(main.autoteste(pasta), main.SAIDA_OK)
            resultado = json.loads((Path(pasta) / 'autoteste.json').read_text(encoding='utf-8'))
            self.assertTrue(resultado['ok'])
            self.assertIsInstance(resultado['tcl_library'], str)

    def test_fluxo_janela(self):
        with (
            tempfile.TemporaryDirectory() as pasta,
            patch('interface.messagebox.showinfo'),
            patch('interface.messagebox.showwarning'),
        ):
            arquivo = Path(pasta) / 'configuração com espaços.dat'
            arquivo.write_text('EDF;2;2\na;FF0000;0;2;5;5\nb;00FF00;0;3;7;7', encoding='utf-8')
            app = Aplicacao(str(arquivo), perguntar_arquivo=False)
            app.raiz.withdraw()
            try:
                app.passo()
                self.assertEqual(app.sim.relogio, 1)

                app.voltar()
                self.assertEqual(app.sim.relogio, 0)

                app.sim.suspender('a')
                app._apos_edicao()
                app.passo()
                self.assertEqual(app.sim.estado.tarefas['a'].estado, Estado.SUSPENSA)

                app.sim.retomar('a')
                app._apos_edicao()

                app.executar_completo()
                limite = time.monotonic() + 30
                while app.completo and time.monotonic() < limite:
                    app.raiz.update()
                self.assertFalse(app.completo, 'Lote completo não terminou')
                self.assertTrue(app.sim.terminou)
                self.assertTrue(arquivo.with_name(arquivo.stem + '_gantt.svg').exists())
                self.assertTrue(app.canvas.find_all())
                self.assertEqual(len(app.tv.get_children()), 2)
            finally:
                app._fechar()


if __name__ == '__main__':
    unittest.main(verbosity=2)
