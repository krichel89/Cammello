"""Static guard against the 'lost module import' class of bugs.

The package split (0.9.x) moved code out of the old monolith, where every
module-level import (os, QSettings, MediaWikiApi, ...) was visible everywhere.
Some of those imports were not carried over, which only blew up at runtime
(NameError inside a slot, swallowed into a dialog). This test walks the AST of
every module and asserts that every global name it loads actually resolves in
that module's namespace after import.
"""
import ast
import builtins
import importlib
import os
import pathlib
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

# Auto-discovered so a new module cannot be forgotten (the hardcoded list
# from 0.9.9 was already missing iptc/mw_iptc/ftp_workers).
MODULES = sorted(
    f.stem for f in (pathlib.Path(__file__).parent / 'cammello').glob('*.py')
    if f.stem != '__init__')

HERE = pathlib.Path(__file__).parent


def _bound_names(tree):
    """Every name bound somewhere in the module (rough but generous)."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)          # covers lambda defaults, e.g. w=worker
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name != '*':
                    names.add(alias.asname or alias.name.split('.')[0])
        elif isinstance(node, ast.Global) or isinstance(node, ast.Nonlocal):
            names.update(node.names)
    return names


def main():
    problems = []
    for mod in MODULES:
        m = importlib.import_module(f'cammello.{mod}')
        tree = ast.parse((HERE / 'cammello' / f'{mod}.py').read_text())
        available = set(vars(m)) | set(dir(builtins)) | _bound_names(tree)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
                    and node.id not in available):
                problems.append(f'{mod}.py:{node.lineno}: {node.id} is not defined')

    for p in problems:
        print('FAIL', p)
    if not problems:
        print('PASS all modules: no unresolved global names')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
