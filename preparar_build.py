"""Prepara as ferramentas locais de construção."""

from pathlib import Path
import subprocess
import sys
import venv


def main():
    """Prepara as ferramentas na pasta do projeto."""
    root = Path(__file__).resolve().parent
    if sys.platform != 'win32' or sys.maxsize <= 2**32:
        raise SystemExit('Este preparo foi definido para Windows x64. Use um Python de 64 bits.')

    import tkinter
    print('Python:', sys.version, '| Tk:', tkinter.TkVersion)

    ambiente = root / '.venv'
    if not (ambiente / 'Scripts/python.exe').exists():
        venv.EnvBuilder(with_pip=True).create(ambiente)

    binarios = ambiente / 'Scripts'
    python = binarios / 'python.exe'
    subprocess.run([str(python), '-m', 'pip', 'install', '-r',
                    str(root / 'requirements-build.txt')], check=True)

    subprocess.run([str(binarios / 'cmake.exe'), '-S', str(root), '-B', str(root / 'build_cmake'),
                    '-G', 'Ninja', f'-DPython3_EXECUTABLE={python}',
                    f'-DCMAKE_MAKE_PROGRAM={binarios / "ninja.exe"}'], check=True)

    print('Preparação concluída. Para construir, execute:')
    print(r'.\.venv\Scripts\cmake.exe --build build_cmake')


if __name__ == '__main__':
    main()
