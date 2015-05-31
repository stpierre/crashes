"""Collect command classes."""

__all__ = []

import pkgutil
import inspect

for loader, name, _ in pkgutil.walk_packages(__path__):
    module = loader.find_module(name).load_module(name)

    for name, value in inspect.getmembers(module):
        if not isinstance(value, type) or name.startswith('__'):
            continue

        globals()[name] = value
        __all__.append(name)
