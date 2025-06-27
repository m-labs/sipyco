"""
This module provides serialization and deserialization functions for Python
objects. Its main features are:

* Human-readable format, fully compatible with JSON.
* Can be serialized on a single line (for framing), with only ASCII characters.
* Supports all basic Python data structures: None, booleans, integers,
  floats, complex numbers, strings, tuples, lists, dictionaries, sets.
* Type fidelity: Data types are accurately reconstructed and decode(encode())
  round trips maintain types. Tuples do not become lists, and dictionary keys
  are not turned into strings.
* Supports Numpy arrays and scalars. (Converted to be C-contiguous as required.)
* Extensible with custom type encoders/decoders.
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
    """Wrap certain Python types to prevent coercion by `json`.

    This recursively walks the three container types known to JSON (dict, list, tuple)
    and wraps tuples in the custom `Tuple` type and dicts with non-str keys in the
    custom `Dict` type.

    If you implement PYON for a custom type with `register_type(), use this on your
    inner values in the `encode()` handler.
    """
    if isinstance(o, dict):
        if not all(isinstance(k, str) for k in o):
            return Dict([[wrap(k), wrap(v)] for k, v in o.items()])
        else:
            return {k: wrap(v) for k, v in o.items()}
    elif isinstance(o, tuple):
        return Tuple([wrap(v) for v in o])
    elif isinstance(o, list):
        return [wrap(v) for v in o]
    else:
        return o


_encode_map = {}
_decode_map = {}


def register(types, *, name, encode, decode):
    """Register custom Python types for encoding and decoding

    Args:
        types (iterable of types): Types to support by the encoder/decoder pair.
        name (str): Unique name to hook the decoder.
        encode (callable): Convert a value to arguments.
            Called with of a type from `types`.
            Returns a list of PYON-encodable arguments for `decode()`.
            Use `wrap()` to prevent coercion of tuples and non-str dicts.
        decode (callable): Convert arguments to a value.
            Called with the PYON-decoded arguments from `encode()`.
            Returns a value of a type from `types`.
    """
    assert all(t not in _encode_map for t in types)
    assert name not in _decode_map
    for t in types:
        _encode_map[t] = name, encode
    _decode_map[name] = decode


def deregister(types, name):
    """Deregister a set of types from the registry"""
    assert all(_encode_map[t][0] == name for t in types)
    del _decode_map[name]
    for t in types:
        del _encode_map[t]


# Custom wrapper types to prevent coercion
register([Tuple], name="tuple", encode=lambda x: [x.data], decode=tuple)
register([Dict], name="dict", encode=lambda x: [x.data], decode=dict)

# Additional PYON-supported types
register([complex], name="complex", encode=lambda x: [x.real, x.imag], decode=complex)
register(
    [bytes],
    name="bytes",
    encode=lambda x: [base64.b64encode(x).decode()],
    decode=base64.b64decode,
)
register([set], name="set", encode=lambda x: [[wrap(v) for v in x]], decode=set)
register(
    [slice],
    name="slice",
    encode=lambda x: [wrap(x.start), wrap(x.stop), wrap(x.step)],
    decode=slice,
)
register(
    [Fraction],
    name="fraction",
    encode=lambda x: [x.numerator, x.denominator],
    decode=Fraction,
)
register(
    [OrderedDict],
    name="ordered_dict",
    encode=lambda x: [[[wrap(k), wrap(v)] for k, v in x.items()]],
    decode=OrderedDict,
)


def _encode_nparray(x):
    return [
        list(x.shape),
        x.dtype.str,
        base64.b64encode(numpy.ascontiguousarray(x).data).decode(),
    ]


def _decode_nparray(shape, dtype, data):
    return numpy.frombuffer(base64.b64decode(data), dtype).copy().reshape(shape)


register(
    [numpy.ndarray],
    name="nparray",
    encode=_encode_nparray,
    decode=_decode_nparray,
)


_np_types = {
    "bool",
    "bytes_",
    "str_",
    "int8",
    "int16",
    "int32",
    "int64",
    "uint8",
    "uint16",
    "uint32",
    "uint64",
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
}


def _encode_npscalar(x):
    return [x.dtype.str, base64.b64encode(x.data).decode()]


def _decode_npscalar(dtype, data):
    return numpy.frombuffer(base64.b64decode(data), dtype)[0]


register(
    [getattr(numpy, t) for t in _np_types],
    name="npscalar",
    encode=_encode_npscalar,
    decode=_decode_npscalar,
)


assert set(name for name, _ in _encode_map.values()) == set(_decode_map.keys())


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
