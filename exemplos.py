"""Configurações de exemplo em arquivos, basta executar python exemplos.py que já gera os arquivos
(é só pra caber no moodle)
"""

from pathlib import Path

# Cada conteúdo abaixo corresponde a um arquivo de configuração do projeto.
ARQUIVOS = {
    'exemplo_avisos.txt': (
        '# Este arquivo CARREGA, mas gera avisos (aba "Avisos"): campos opcionais ausentes recebem valores\n'
        '# padrão, tarefa aperiódica (período 0) é ignorada no Projeto A e ids BS/PS/DS/SS são tratados\n'
        '# como tarefas periódicas comuns.\n'
        'rm;3;2\n'
        'A;FF0000;0;2;6;6;\n'
        'b;;1;1;4;;\n'
        'C;00FF00;0;3;0;5;\n'
        'BS01;0000FF;0;1;8;8;\n'
    ),

    'exemplo_desempate.txt': (
        '# Desempate: t01, t02 e t03 são idênticas (mesmo prazo, ingresso e duração), então o escalonador\n'
        '# recorre ao critério 5 (sorteio). Cada sorteio aparece no Gantt com o ícone de dado.\n'
        '# Com a mesma semente (--semente) o resultado se repete, mude a semente para ver outro sorteio.\n'
        'EDF;2;1\n'
        't01;E6194B;0;2;10;10;\n'
        't02;3CB44B;0;2;10;10;\n'
        't03;4363D8;0;2;10;10;\n'
        't04;F58231;0;1;5;5;\n'
    ),

    'exemplo_edf_2cpus.txt': (
        '# Exemplo principal: EDF global com 2 processadores (quantum 2).\n'
        '# Formato: algoritmo_escalonamento,quantum,qtde_cpus\n'
        'EDF;2;2\n'
        '# id,cor,ingresso,duracao,periodo,prazo,lista_eventos\n'
        't01;E6194B;0;2;5;5;\n'
        't02;3CB44B;0;3;7;7;\n'
        't03;4363D8;1;2;10;8;\n'
        't04;F58231;0;4;12;12;\n'
    ),

    'exemplo_erros.txt': (
        '# Este arquivo NÃO carrega: mostra as mensagens de erro (todas de uma vez, com o número da linha).\n'
        'XYZ;0;0\n'
        't01;E6194B;0;2;-5;5;\n'
        't01;3CB44B;0;3;7;7;\n'
        't03;ZZZZZZ;0;2;10;8;\n'
        't04;4363D8;a;2;10;8;\n'
        't05;4363D8;0;0;10;8;\n'
    ),

    'exemplo_horizonte_longo.txt': (
        '# Dez ocorrências: término em 270001, além do antigo limite de 200000 ticks.\n'
        '# Exporte pelo modo completo, o SVG terá largura grande por representar tudo.\n'
        'EDF;1;1\n'
        'a;FF0000;0;1;30000;30000\n'
    ),

    'exemplo_ingresso.txt': (
        '# Em t=12, a vence b pelo ingresso original (0 < 5), embora tenha reativado em 10.\n'
        'EDF;1;1\n'
        'a;FF0000;0;1;10;10\n'
        'b;00FF00;5;1;100;15\n'
        'x;0000FF;5;7;100;8\n'
    ),

    'exemplo_rm_perde_prazo.txt': (
        '# RM com 1 processador: utilização 2/5 + 4/7 = 0,97 > 0,83 (limite de Liu & Layland para 2 tarefas).\n'
        '# t02 perde prazos (marcados com X vermelho no Gantt) e continua executando até terminar.\n'
        '# Troque o algoritmo para EDF (Editar > Sistema) e veja o mesmo conjunto cumprir todos os prazos.\n'
        'RM;2;1\n'
        't01;E6194B;0;2;5;5;\n'
        't02;4363D8;0;4;7;7;\n'
    ),

    'exemplo_sobreposicao.txt': (
        '# C > T é permitido: ocorrências atrasadas são acumuladas e continuam executando.\n'
        'EDF;2;2\n'
        'a;E6194B;0;5;3;3\n'
        'b;4363D8;0;1;4;4\n'
    ),

    '.vscode/launch.json': (
        '{\n'
        '  "version": "0.2.0",\n'
        '  "configurations": [\n'
        '    {\n'
        '      "name": "Simulador — interface",\n'
        '      "type": "debugpy",\n'
        '      "request": "launch",\n'
        '      "program": "${workspaceFolder}/main.py",\n'
        '      "python": "${workspaceFolder}/.venv/Scripts/python.exe",\n'
        '      "cwd": "${workspaceFolder}",\n'
        '      "console": "integratedTerminal",\n'
        '      "justMyCode": true,\n'
        '      "args": [\n'
        '        "${workspaceFolder}/exemplo_edf_2cpus.txt"\n'
        '      ]\n'
        '    },\n'
        '    {\n'
        '      "name": "Simulador — escolher arquivo",\n'
        '      "type": "debugpy",\n'
        '      "request": "launch",\n'
        '      "program": "${workspaceFolder}/main.py",\n'
        '      "python": "${workspaceFolder}/.venv/Scripts/python.exe",\n'
        '      "cwd": "${workspaceFolder}",\n'
        '      "console": "integratedTerminal",\n'
        '      "justMyCode": true,\n'
        '      "args": []\n'
        '    },\n'
        '    {\n'
        '      "name": "Simulador — completo RM",\n'
        '      "type": "debugpy",\n'
        '      "request": "launch",\n'
        '      "program": "${workspaceFolder}/main.py",\n'
        '      "python": "${workspaceFolder}/.venv/Scripts/python.exe",\n'
        '      "cwd": "${workspaceFolder}",\n'
        '      "console": "integratedTerminal",\n'
        '      "justMyCode": true,\n'
        '      "args": [\n'
        '        "${workspaceFolder}/exemplo_rm_perde_prazo.txt",\n'
        '        "--completo",\n'
        '        "--saida",\n'
        '        "${workspaceFolder}/resultado_rm.svg"\n'
        '      ]\n'
        '    }\n'
        '  ]\n'
        '}\n'
    ),

    '.vscode/settings.json': (
        '{\n'
        '  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/Scripts/python.exe",\n'
        '  "python.testing.unittestEnabled": true,\n'
        '  "python.testing.pytestEnabled": false,\n'
        '  "python.testing.unittestArgs": [\n'
        '    "-v",\n'
        '    "-s",\n'
        '    ".",\n'
        '    "-p",\n'
        '    "testes*.py"\n'
        '  ],\n'
        '  "python.testing.cwd": "${workspaceFolder}",\n'
        '  "files.encoding": "utf8",\n'
        '  "files.exclude": {\n'
        '    "**/__pycache__": true,\n'
        '    ".venv": true,\n'
        '    "build_cmake": true\n'
        '  },\n'
        '  "python.analysis.exclude": [\n'
        '    ".venv",\n'
        '    "build_cmake",\n'
        '    "dist"\n'
        '  ]\n'
        '}\n'
    ),

    '.vscode/tasks.json': (
        '{\n'
        '  "version": "2.0.0",\n'
        '  "tasks": [\n'
        '    {\n'
        '      "label": "Testar núcleo e regressões",\n'
        '      "type": "process",\n'
        '      "command": "${workspaceFolder}/.venv/Scripts/python.exe",\n'
        '      "args": [\n'
        '        "-B",\n'
        '        "-m",\n'
        '        "unittest",\n'
        '        "testes",\n'
        '        "testes_regressao",\n'
        '        "-v"\n'
        '      ],\n'
        '      "options": {\n'
        '        "cwd": "${workspaceFolder}"\n'
        '      },\n'
        '      "problemMatcher": []\n'
        '    },\n'
        '    {\n'
        '      "label": "Testar interface",\n'
        '      "type": "process",\n'
        '      "command": "${workspaceFolder}/.venv/Scripts/python.exe",\n'
        '      "args": [\n'
        '        "-B",\n'
        '        "-m",\n'
        '        "unittest",\n'
        '        "testes_interface",\n'
        '        "-v"\n'
        '      ],\n'
        '      "options": {\n'
        '        "cwd": "${workspaceFolder}"\n'
        '      },\n'
        '      "problemMatcher": []\n'
        '    },\n'
        '    {\n'
        '      "label": "Testar horizonte longo",\n'
        '      "type": "process",\n'
        '      "command": "${workspaceFolder}/.venv/Scripts/python.exe",\n'
        '      "args": [\n'
        '        "-B",\n'
        '        "-m",\n'
        '        "unittest",\n'
        '        "testes_longos",\n'
        '        "-v"\n'
        '      ],\n'
        '      "options": {\n'
        '        "cwd": "${workspaceFolder}"\n'
        '      },\n'
        '      "problemMatcher": []\n'
        '    },\n'
        '    {\n'
        '      "label": "Construir executável (CMake)",\n'
        '      "type": "process",\n'
        '      "command": "${workspaceFolder}/.venv/Scripts/cmake.exe",\n'
        '      "args": [\n'
        '        "--build",\n'
        '        "${workspaceFolder}/build_cmake"\n'
        '      ],\n'
        '      "options": {\n'
        '        "cwd": "${workspaceFolder}"\n'
        '      },\n'
        '      "problemMatcher": [],\n'
        '      "group": {\n'
        '        "kind": "build",\n'
        '        "isDefault": true\n'
        '      }\n'
        '    }\n'
        '  ]\n'
        '}\n'
    ),
}


def gerar(destino=None):
    """Cria os exemplos sem sobrescrever o que já foi editado."""
    raiz = Path(destino) if destino is not None else Path(__file__).resolve().parent
    for nome, conteudo in ARQUIVOS.items():
        caminho = raiz / nome
        caminho.parent.mkdir(parents=True, exist_ok=True)
        if not caminho.exists():
            caminho.write_text(conteudo, encoding='utf-8')
    return raiz


if __name__ == '__main__':
    print('Configurações disponíveis em:', gerar())
