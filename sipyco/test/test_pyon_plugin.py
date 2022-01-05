import dataclasses

import pluggy
import pytest

import sipyco
import sipyco.hookspecs as hookspecs
import sipyco.plugins as plugin
import sipyco.pyon as pyon


@dataclasses.dataclass
class Point:
    x: float
    y: float


class TestPyonPlugin:
    @sipyco.hookimpl
    def sipyco_pyon_encode(value, pretty=False):
        if isinstance(value, Point):
            return repr(value)

    @sipyco.hookimpl
    def sipyco_pyon_decoders():
        return [("Point", Point)]


def test_pyon_plugin_fail_without_plugin():
    with pytest.raises(TypeError):
        pyon.encode(Point(3, 4))


def pyon_extra_plugin():
    pm = pluggy.PluginManager("sipyco")
    pm.add_hookspecs(sipyco.hookspecs)
    pm.register(pyon)
    pm.load_setuptools_entrypoints("sipyco")
    pm.register(TestPyonPlugin)
    return pm


def test_pyon_plugin_encode(monkeypatch):
    monkeypatch.setattr(plugin, "get_plugin_manager", pyon_extra_plugin)
    assert pyon.encode(Point(2, 3)) == "Point(x=2, y=3)"


def test_pyon_plugin_encode_decode(monkeypatch):
    monkeypatch.setattr(plugin, "get_plugin_manager", pyon_extra_plugin)
    test_value = Point(2.5, 3.4)
    assert pyon.decode(pyon.encode(test_value)) == test_value


def test_pyon_nested_encode(monkeypatch):
    """Tests that nested items will be properly encoded."""
    monkeypatch.setattr(plugin, "get_plugin_manager", pyon_extra_plugin)
    test_value = {"first": Point(2.5, {"nothing": 0})}
    assert pyon.decode(pyon.encode(test_value)) == test_value
