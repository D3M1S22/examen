"""Both storage backends keep the signatures of AbstractContextStore (docs/next_steps/dynamodb_storage/07 P0)."""

import inspect

import pytest

from src.core.storage.base import AbstractContextStore
from src.core.storage.sqlite_store import SQLiteContextStore


def _public_methods(cls):
    return {
        name: member for name, member in inspect.getmembers(cls, predicate=inspect.isfunction)
        if not name.startswith("_")
    }


def _backends():
    backends = [SQLiteContextStore]
    try:
        from src.core.storage.dynamo_store import DynamoContextStore
    except ImportError:  # pragma: no cover - before P1
        return backends
    return backends + [DynamoContextStore]


def test_every_interface_method_is_abstract():
    concrete = [name for name, fn in _public_methods(AbstractContextStore).items()
                if not getattr(fn, "__isabstractmethod__", False)]
    assert concrete == []


@pytest.mark.parametrize("backend", _backends(), ids=lambda c: c.__name__)
def test_backend_matches_interface(backend):
    interface = _public_methods(AbstractContextStore)
    implemented = _public_methods(backend)
    extra = sorted(set(implemented) - set(interface))
    assert extra == [], f"{backend.__name__} has public methods outside the interface: {extra}"
    for name, abstract in interface.items():
        assert name in implemented, f"{backend.__name__} misses {name}"
        expected = inspect.signature(abstract)
        actual = inspect.signature(implemented[name])
        assert list(actual.parameters) == list(expected.parameters), f"{backend.__name__}.{name}: {actual} != {expected}"
        for param in expected.parameters.values():
            assert actual.parameters[param.name].default == param.default, f"{backend.__name__}.{name}.{param.name}"
