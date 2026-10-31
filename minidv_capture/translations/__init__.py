"""Load the available UI translations from one module per language."""

from importlib import import_module
from pkgutil import iter_modules
from pathlib import Path


def load_languages():
    languages = {}
    for module in iter_modules([str(Path(__file__).parent)]):
        if module.name.startswith('_'):
            continue
        catalog = import_module(f'.{module.name}', __name__)
        languages[catalog.CODE] = {
            'name': catalog.NAME,
            'flag': catalog.FLAG,
            'strings': catalog.STRINGS,
        }
    return languages


LANGUAGES = load_languages()
