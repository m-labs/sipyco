import typing

import pluggy


hookspec = pluggy.HookspecMarker("sipyco")


@hookspec(firstresult=True)
def sipyco_pyon_encode(value: typing.Any, pretty: bool, indent_level: int) -> str:
    """Encode a python object to a PYON string."""


@hookspec
def sipyco_pyon_decoders() -> typing.Sequence[typing.Tuple[str, typing.Any]]:
    """Return elements for the decoding dictionary (passed to eval).

    The return value should be a sequence of tuples, to allow one plugin function
    to return multiple types that it can decode. Each tuple is the 'name' of the
    value (in PYON) and the Python value (e.g. ``('pi', np.pi)``).
    """
