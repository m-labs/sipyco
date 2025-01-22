"""
This module provides serialization and deserialization functions for Python
objects. Its main features are:

* Human-readable format compatible with the Python syntax.
* Each object is serialized on a single line, with only ASCII characters.
* Supports all basic Python data structures: None, booleans, integers,
  floats, complex numbers, strings, tuples, lists, dictionaries.
* Those data types are accurately reconstructed (unlike JSON where e.g. tuples
  become lists, and dictionary keys are turned into strings).
* Supports Numpy arrays. (Converted to be C-contiguous as required.)

The main rationale for this new custom serializer (instead of using JSON) is
that JSON does not support Numpy and more generally cannot be extended with
other data types while keeping a concise syntax. Here we can use the Python
function call syntax to express special data types.
"""


from operator import itemgetter
from fractions import Fraction
from collections import OrderedDict
import io
import json
import os
import tempfile

import numpy
try:
    import pybase64 as base64
except ImportError:
    import base64


_encode_map = {
    type(None): "none",
    bool: "bool",
    int: "number",
    float: "number",
    complex: "number",
    str: "str",
    bytes: "bytes",
    tuple: "tuple",
    list: "list",
    set: "set",
    dict: "dict",
    slice: "slice",
    Fraction: "fraction",
    OrderedDict: "ordereddict",
    numpy.ndarray: "nparray"
}

_numpy_scalar = {
    "int8", "int16", "int32", "int64",
    "uint8", "uint16", "uint32", "uint64",
    "float16", "float32", "float64",
    "complex64", "complex128",
}


for _t in _numpy_scalar:
    _encode_map[getattr(numpy, _t)] = "npscalar"


class _Encoder:
    __slots__ = ("pretty", "indent_level", "out")

    def __init__(self, pretty):
        self.pretty = pretty
        self.indent_level = 0
        self.out = []

    def get_output(self):
        return "".join(self.out)

    def indent(self):
        return "    "*self.indent_level

    def encode_none(self, x):
        self.out.append("null")

    def encode_bool(self, x):
        if x:
            self.out.append("true")
        else:
            self.out.append("false")

    def encode_number(self, x):
        self.out.append(repr(x))

    def encode_str(self, x):
        # Do not use repr() for JSON compatibility.
        self.out.append(json.dumps(x))

    def encode_bytes(self, x):
        self.out.append(repr(x))

    def _encode_sequence(self, start, end, x):
        self.out.append(start)
        first = True
        for item in x:
            if not first:
                self.out.append(", ")
            first = False

            self.encode(item)
        self.out.append(end)

    def encode_tuple(self, x):
        if len(x) == 1:
            self.out.append("(")
            self.encode(x[0])
            self.out.append(", )")
        else:
            self._encode_sequence("(", ")", x)

    def encode_list(self, x):
        self._encode_sequence("[", "]", x)

    def encode_set(self, x):
        self._encode_sequence("{", "}", x)

    def encode_dict(self, x):
        if self.pretty and all(k.__class__ == str for k in x.keys()):
            items = lambda: sorted(x.items(), key=itemgetter(0))
        else:
            items = x.items

        self.out.append("{")
        if not self.pretty or len(x) < 2:
            first = True
            for k, v in items():
                if not first:
                    self.out.append(", ")
                first = False

                self.encode(k)
                self.out.append(": ")
                self.encode(v)
        else:
            self.indent_level += 1
            self.out.append("\n")
            indent = self.indent()
            first = True
            for k, v in items():
                if not first:
                    self.out.append(",\n")
                first = False

                self.out.append(indent)
                self.encode(k)
                self.out.append(": ")
                self.encode(v)

            self.out.append("\n")

            self.indent_level -= 1
            self.out.append(self.indent())

        self.out.append("}")

    def encode_slice(self, x):
        self.out.append(repr(x))

    def encode_fraction(self, x):
        self.out.append("Fraction(")
        self.encode(x.numerator)
        self.out.append(", ")
        self.encode(x.denominator)
        self.out.append(")")

    def encode_ordereddict(self, x):
        self.out.append("OrderedDict(")
        self.encode_list(x.items())
        self.out.append(")")

    def encode_nparray(self, x):
        if numpy.ndim(x) > 0:
            x = numpy.ascontiguousarray(x)
        self.out.append("nparray(")
        self.encode(x.shape)
        self.out.append(", ")
        self.encode(x.dtype.str)
        self.out.append(", b\"")
        self.out.append(base64.b64encode(x.data).decode())
        self.out.append("\")")

    def encode_npscalar(self, x):
        self.out.append("npscalar(")
        self.encode(x.dtype.str)
        self.out.append(", b\"")
        self.out.append(base64.b64encode(x.data).decode())
        self.out.append("\")")

    def encode(self, x):
        ty = _encode_map.get(type(x), None)
        if ty is None:
            if isinstance(x, dict):
                ty = "dict"
            else:
                raise TypeError("`{!r}` ({}) is not PYON serializable"
                                .format(x, type(x)))
        getattr(self, "encode_" + ty)(x)


def encode(x, pretty=False):
    """Serializes a Python object and returns the corresponding string in
    Python syntax."""
    encoder = _Encoder(pretty)
    encoder.encode(x)
    return encoder.get_output()


def _nparray(shape, dtype, data):
    a = numpy.frombuffer(base64.b64decode(data), dtype=dtype)
    a = a.copy()
    return a.reshape(shape)


def _npscalar(ty, data):
    return numpy.frombuffer(base64.b64decode(data), dtype=ty)[0]


_eval_dict = {
    "__builtins__": {},

    "null": None,
    "false": False,
    "true": True,
    "inf": numpy.inf,
    "slice": slice,
    "nan": numpy.nan,

    "Fraction": Fraction,
    "OrderedDict": OrderedDict,
    "nparray": _nparray,
    "npscalar": _npscalar
}


def decode(s):
    """
    Parses a string in the Python syntax, reconstructs the corresponding
    object, and returns it.
    **Shouldn't** be used with untrusted inputs, as it can cause vulnerability against injection attacks.
    """
    return eval(s, _eval_dict, {})


def store_file(filename, x):
    """Encodes a Python object and writes it to the specified file."""
    contents = encode(x, True)
    directory = os.path.abspath(os.path.dirname(filename))
    with tempfile.NamedTemporaryFile("w", dir=directory, delete=False, encoding="utf-8") as f:
        f.write(contents)
        f.write("\n")
        tmpname = f.name
    os.replace(tmpname, filename)


def load_file(filename):
    """Parses the specified file and returns the decoded Python object."""
    with open(filename, "r", encoding="utf-8") as f:
        return decode(f.read())
