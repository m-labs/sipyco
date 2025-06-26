"""
This module provides serialization and deserialization functions for Python
objects. Its main features are:

* Human-readable format, fully compatible with JSON.
* Each object is serialized on a single line, with only ASCII characters.
* Supports all basic Python data structures: None, booleans, integers,
  floats, complex numbers, strings, tuples, lists, dictionaries.
* Data types are accurately reconstructed and decode(encode()) round trips
  maintain types. Tuples do not become lists, and dictionary keys are
  not turned into strings.
* Supports Numpy arrays and scalars. (Converted to be C-contiguous as required.)
"""

from fractions import Fraction
from collections import OrderedDict
import json
import os
import tempfile

import numpy

try:
    import pybase64 as base64
except ImportError:
    import base64


class Dict:
    def __init__(self, data):
        self.data = data


class Tuple:
    def __init__(self, data):
        self.data = data


def wrap(o):
    if isinstance(o, dict):
        o = {wrap(k): wrap(v) for k, v in o.items()}
        if not all(isinstance(k, str) for k in o):
            o = Dict(o)
    elif isinstance(o, tuple):
        o = Tuple(tuple(wrap(v) for v in o))
    elif isinstance(o, list):
        o = [wrap(v) for v in o]
    elif isinstance(o, set):
        o = {wrap(v) for v in o}
    elif isinstance(o, slice):
        o = slice(wrap(o.start), wrap(o.stop), wrap(o.step))
    elif isinstance(o, OrderedDict):
        o = OrderedDict((wrap(k), wrap(v)) for k, v in o.items())
    return o


_encode_map = {
    Tuple: ("tuple", lambda x: [list(x.data)]),
    Dict: ("dict", lambda x: [list(x.data.items())]),
    complex: ("complex", lambda x: [x.real, x.imag]),
    bytes: ("bytes", lambda x: [base64.b64encode(x).decode()]),
    set: ("set", lambda x: [list(x)]),
    slice: ("slice", lambda x: [x.start, x.stop, x.step]),
    Fraction: ("fraction", lambda x: [x.numerator, x.denominator]),
    OrderedDict: ("ordered_dict", lambda x: [list(x.items())]),
}


def _encode_nparray(x):
    if numpy.ndim(x) > 0:
        x = numpy.ascontiguousarray(x)
    return [list(x.shape), x.dtype.str, base64.b64encode(x.data).decode()]


for _t in {
    "ndarray",
    "bool",
    "bytes_",
    "str_",
    "int8",
    "int16",
    "int32",
    "int64",
    "intp",
    "uint8",
    "uint16",
    "uint32",
    "uint64",
    "uintp",
    "float16",
    "float32",
    "float64",
    "float128",
    "complex64",
    "complex128",
    "complex256",
    "timedelta64",
    "datetime64",
    "void",
}:
    _encode_map[getattr(numpy, _t)] = ("ndarray", _encode_nparray)


class _Encoder(json.JSONEncoder):
    def default(self, o):
        try:
            ty, enc = _encode_map[type(o)]
        except KeyError:
            raise TypeError("`{!r}` ({}) is not PYON serializable".format(o, type(o)))
        return {"__jsonclass__": [ty, enc(o)]}


def encode(x, pretty=False):
    """Serializes a Python object and returns the corresponding string in
    PYON syntax."""
    if pretty:
        indent = 4
        separators = None
    else:
        indent = None
        separators = (",", ":")
    return json.dumps(wrap(x), cls=_Encoder, indent=indent, separators=separators)


def _decode_nparray(shape, dtype, data):
    return numpy.frombuffer(base64.b64decode(data), dtype).copy().reshape(shape)


_decode_map = {
    "complex": complex,
    "bytes": base64.b64decode,
    "tuple": tuple,
    "slice": slice,
    "set": set,
    "fraction": Fraction,
    "dict": dict,
    "ndarray": _decode_nparray,
    "ordered_dict": OrderedDict,
}


assert set(name for name, _ in _encode_map.values()) == set(_decode_map.keys())


def _object_hook(s):
    try:
        dec, args = s["__jsonclass__"]
    except KeyError:
        return s
    return _decode_map[dec](*args)


def decode(s):
    """
    Parses a PYON string, reconstructs the corresponding
    object, and returns it.
    """
    return json.loads(s, object_hook=_object_hook)


def store_file(filename, x):
    """Encodes a Python object and writes it to the specified file."""
    directory = os.path.abspath(os.path.dirname(filename))
    with tempfile.NamedTemporaryFile(
        "w", dir=directory, delete=False, encoding="utf-8"
    ) as f:
        json.dump(wrap(x), f, cls=_Encoder, indent=4)
        tmpname = f.name
    os.replace(tmpname, filename)


def load_file(filename):
    """Parses the specified file and returns the decoded Python object."""
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f, object_hook=_object_hook)
