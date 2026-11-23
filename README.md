# Simulador de escalonamento de tarefas de tempo real

Projeto A da disciplina de Sistemas Operacionais (UTFPR), feito em equipe por Enzo Daneluk e Theo.

O programa lê um arquivo de configuração com um conjunto de tarefas periódicas, simula o escalonamento em uma ou mais CPUs e desenha o diagrama de Gantt. Serve para ver na prática quando o Rate Monotonic perde prazo, como o EDF distribui tarefas entre dois processadores e como ficam desempates e ingressos tardios.

## Funcionalidades

- Algoritmos RM (Rate Monotonic) e EDF (Earliest Deadline First), com suporte a várias CPUs
- Novos algoritmos podem ser adicionados como plugin (`escalonadores.py`, função `carregar_plugin`)
- Interface gráfica em Tkinter para editar tarefas, executar passo a passo e exportar o Gantt
- Modo de linha de comando que roda a simulação inteira e gera o SVG sem abrir janela
- Validação do arquivo de entrada com mensagens de erro e aviso por linha
- Testes unitários, de regressão e de interface

## Estrutura

```
main.py              ponto de entrada (interface ou linha de comando)
interface.py         janela principal
edicao.py, dialogos.py   edição de tarefas e caixas de diálogo
simulador.py         núcleo da simulação (relógio, estados, eventos)
escalonadores.py     RM, EDF e carga de plugins
modelo.py            TCB, estados e constantes
config.py            leitura e validação da configuração
gantt.py             geração do diagrama em SVG
exemplos.py          configurações de exemplo
testes*.py           testes unitários, de regressão, longos e de interface
exemplo_*.txt        cenários de entrada
exemplo_*_gantt.svg  saídas geradas a partir dos cenários
construir.py         empacotamento com PyInstaller
Makefile, CMakeLists.txt  atalhos de build e teste
```

## Formato da entrada

```
# algoritmo;quantum;qtde_cpus
EDF;2;2
# id;cor;ingresso;duracao;periodo;prazo;lista_eventos
t01;E6194B;0;2;5;5;
t02;3CB44B;0;3;7;7;
```

## Tecnologias

Python 3 (testado com 3.13), Tkinter, SVG gerado à mão, unittest, PyInstaller, Make e CMake.

## Como executar

```bash
# interface gráfica
python main.py exemplo_edf_2cpus.txt

# simulação completa sem janela, exportando o Gantt
python main.py exemplo_edf_2cpus.txt --completo --saida gantt.svg

# imprimir uma configuração de exemplo
python main.py --exemplo

# testes
make test        # ou: python -B -m unittest testes testes_regressao -v

# gerar executável (requer as dependências de requirements-build.txt)
pip install -r requirements-build.txt
python construir.py
```
