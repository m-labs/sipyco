"""
This module provides serialization and deserialization functions for Python
objects. Its main features are:

* Human-readable format, fully compatible with JSON. PYON _is_ JSON.
* Can be serialized on a single line (for framing), with only ASCII characters.
* Supports all basic Python data structures: None, booleans, integers,
  floats, complex numbers, strings, tuples, lists, dictionaries, sets.
* Type fidelity: values are accurately reconstructed and decode(encode())
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
import sys

import numpy

try:
    import pybase64 as base64
except ImportError:
    import base64

_jsonclass = sys.intern("__jsonclass__")


class _Dict:
    def __init__(self, data):
        self.data = data


class _Tuple:
    def __init__(self, data):
        self.data = data


def wrap(o):
    """Wrap certain Python types to prevent coercion by `json`

    This recursively walks the three container types known to JSON (dict, list, tuple)
    and wraps dicts with non-str keys and tuples.

    If you implement PYON for a custom type, use this on your
    inner values in the `encode()` handler.
    """
    if isinstance(o, dict):
        assert _jsonclass not in o
        if not all(isinstance(k, str) for k in o):
            return _Dict([[wrap(k), wrap(v)] for k, v in o.items()])
        else:
            return {k: wrap(v) for k, v in o.items()}
    elif isinstance(o, tuple):
        return _Tuple([wrap(v) for v in o])
    elif isinstance(o, list):
        return [wrap(v) for v in o]
    else:
        return o


_encode_map = {}
_decode_map = {}


def register(types, *, name, encode, decode):
    """Register custom types for PYON encoding and decoding

    Args:
        types (iterable of types): Types supported by the encode/decode pair.
        name (str): Unique name to mark the types and hook the decoder.
        encode (callable): Convert a value to arguments.
            Called with a value of a type from `types`.
            Returns a list of PYON-encodable arguments for `decode()`.
            Use `wrap()` to prevent coercion of tuples and non-str dicts.
        decode (callable): Convert arguments to a value.
            Called with the PYON-decoded arguments from `encode()`.
            Returns a value of a type from `types`.
    """
    assert not any(t in _encode_map for t in types)
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
register([_Tuple], name="tuple", encode=lambda x: [x.data], decode=tuple)
register([_Dict], name="dict", encode=lambda x: [x.data], decode=dict)

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
    name="Fraction",
    encode=lambda x: [x.numerator, x.denominator],
    decode=Fraction,
)
register(
    [OrderedDict],
    name="OrderedDict",
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


_numpy_scalar = {
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
    [getattr(numpy, t) for t in _numpy_scalar],
    name="npscalar",
    encode=_encode_npscalar,
    decode=_decode_npscalar,
)


assert set(name for name, _ in _encode_map.values()) == set(_decode_map.keys())


def _encode_default(o):
    try:
        ty, enc = _encode_map[type(o)]
    except KeyError:
        raise TypeError("`{!r}` ({}) is not PYON serializable".format(o, type(o)))
    return {_jsonclass: [ty, enc(o)]}


def encode(x, pretty=False, **kw):
    """Serializes a Python object and returns the corresponding PYON string"""
    if pretty:
        indent = 4
        separators = None
    else:
        indent = None
        separators = (",", ":")
    return json.dumps(
        wrap(x), default=_encode_default, indent=indent, separators=separators, **kw
    )


def _object_hook(s):
    try:
        dec, args = s[_jsonclass]
    except KeyError:
        return s
    return _decode_map[dec](*args)


def decode(s, **kw):
    """Deserializes a PYON string and returns the corresponding object"""
    return json.loads(s, object_hook=_object_hook, **kw)


def store_file(filename, x, **kw):
    """Encodes a Python object and writes it to the specified file

    This makes a good attempt to make the switch as atomic as possible.
    The directory containing `filename` must be writable.
    """
    directory = os.path.abspath(os.path.dirname(filename))
    with tempfile.NamedTemporaryFile(
        "w", dir=directory, delete=False, encoding="utf-8"
    ) as f:
        json.dump(wrap(x), f, default=_encode_default, indent=4, **kw)
        # make sure that all data is on disk
        # see http://stackoverflow.com/questions/7433057/is-rename-without-fsync-safe
        f.flush()
        os.fsync(f.fileno())
        tmpname = f.name
    os.replace(tmpname, filename)


def load_file(filename, **kw):
    """Decodes a Python object from a file"""
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f, object_hook=_object_hook, **kw)


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
    "nparray": _decode_nparray,
    "npscalar": _decode_npscalar,
}


def decode_v1(s):
    """
    Deserializes a PYON v1 string and returns the reconstructed object

    **Shouldn't** be used with untrusted inputs, as it can cause vulnerability against injection attacks.

    This is a convenience function to convert existing PYON v1 to JSON compliant PYON v2.
    """
    return eval(s, _eval_dict, {})


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="""
Convert a PYON v1 file to JSON compliant PYON v2 in place.

A backup of the input file is kept with the `_v1` extension.
""".strip()
    )
    parser.add_argument("file")
    args = parser.parse_args()
    obj = decode_v1(open(args.file, "r", encoding="utf-8").read())
    backup = f"{args.file}_v1"
    assert not os.path.exists(backup), "Backup file already exists. Aborting."
    os.replace(args.file, backup)
    store_file(args.file, obj)
