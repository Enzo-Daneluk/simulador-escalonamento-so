"""Testes, empacotamento e verificação do executável."""

from pathlib import Path
import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent


def executar(*args):
    """Passa os argumentos separados para preservar caminhos com espaços e acentos."""
    print('Executando:', ' '.join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=ROOT, check=True)


def construir(destino, temporarios):
    """Roda os testes, gera o executável e testa o pacote."""
    inicio = time.monotonic()
    import PyInstaller

    executar(sys.executable, '-B', '-m', 'unittest', 'testes', 'testes_regressao', '-v')
    for p in ROOT.glob('*.py'):
        compile(p.read_text(encoding='utf-8'), str(p), 'exec')

    executar(sys.executable, '-m', 'PyInstaller', '--onefile', '--clean', '--noconfirm',
             '--noupx', '--name', 'simulador-rt', '--distpath', destino,
             '--workpath', temporarios / 'pyinstaller', '--specpath', temporarios,
             ROOT / 'main.py')

    exe = destino / ('simulador-rt.exe' if sys.platform == 'win32' else 'simulador-rt')
    executar(exe, '--autoteste', temporarios / 'autoteste')

    manifest = dict(sistema=platform.platform(), arquitetura=platform.machine(),
                    python=sys.version, pyinstaller=PyInstaller.__version__,
                    segundos=round(time.monotonic() - inicio, 2),
                    sha256_executavel=hashlib.sha256(exe.read_bytes()).hexdigest(),
                    fontes={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted(ROOT.glob('*.py'))})
    (destino / 'construcao.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Construção e autoteste concluídos:', exe)


def main():
    """Define as pastas de saída e inicia a construção."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--destino', type=Path, default=ROOT / 'dist')
    p.add_argument('--temporarios', type=Path, default=ROOT / 'build')
    a = p.parse_args()
    destino, temporarios = a.destino.resolve(), a.temporarios.resolve()
    destino.mkdir(parents=True, exist_ok=True)
    temporarios.mkdir(parents=True, exist_ok=True)
    try:
        construir(destino, temporarios)
    except ImportError:
        p.exit(1, 'Ferramenta ausente. Prepare o ambiente com requirements-build.txt antes da defesa.\n')
    except subprocess.CalledProcessError as exc:
        p.exit(exc.returncode or 1, 'Construção interrompida: uma etapa falhou.\n')


if __name__ == '__main__':
    main()
