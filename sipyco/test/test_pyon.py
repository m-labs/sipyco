import unittest
import json
from fractions import Fraction
from collections import OrderedDict
import tempfile

import numpy as np

from sipyco import pyon


_pyon_test_object = {
    None: False,
    True: b"bytes",
    float("inf"): float("-inf"),
    (1, 2): [(3, 4.2), (2, )],
    "slice": slice(3),
    Fraction(3, 4): np.linspace(5, 10, 1),
    "set": {"testing", "sets"},
    "a": np.int8(9), "b": np.int16(-98), "c": np.int32(42), "d": np.int64(-5),
    "e": np.uint8(8), "f": np.uint16(5), "g": np.uint32(4), "h": np.uint64(9),
    "x": np.float16(9.0), "y": np.float32(9.0), "z": np.float64(9.0),
    1j: 1-9j,
    "q": np.complex128(1j),
    "od": OrderedDict(zip(reversed(range(3)), "abc")),
    "unicode": "\u269B",
    "newline": "\n" """
""",
}


class PYON(unittest.TestCase):
    def test_encdec(self):
        for enc in pyon.encode, lambda x: pyon.encode(x, True):
            with self.subTest(enc=enc):
                self.assertEqual(pyon.decode(enc(_pyon_test_object)),
                                 _pyon_test_object)
                # NaNs don't compare equal, so test separately.
                assert np.all(np.isnan(pyon.decode(enc(np.nan))))
                assert np.all(np.isnan(pyon.decode(enc(float("nan")))))

    def test_encdec_array(self):
        orig = {k: (np.array(v), np.array([v]))
                for k, v in _pyon_test_object.items()
                if np.isscalar(v)}
        for enc in pyon.encode, lambda x: pyon.encode(x, True):
            result = pyon.decode(enc(orig))
            for k in orig:
                with self.subTest(enc=enc, k=k, v=orig[k]):
                    np.testing.assert_equal(result[k], orig[k])

    def test_encdec_array_order(self):
        """Test encoding of non c-contiguous arrays (see #5)"""
        array = np.reshape(np.arange(6), (2, 3), order='F')
        np.testing.assert_array_equal(
            array, pyon.decode(pyon.encode(array)))

    def test_file(self):
        with tempfile.NamedTemporaryFile() as f:
            pyon.store_file(f.name, _pyon_test_object)
            readback = pyon.load_file(f.name)
            self.assertEqual(readback, _pyon_test_object)

    def test_single_line(self):
        res = pyon.encode(_pyon_test_object, pretty=False)
        self.assertEqual(len(res.splitlines()), 1)

    def test_jsonclass(self):
        with self.assertRaises(AssertionError):
            pyon.encode({"__jsonclass__": None})

    def test_unsupported(self):
        with self.assertRaises(TypeError):
            pyon.encode(self)
        with self.assertRaises(TypeError):
            pyon.decode("{\"__jsonclass__\": [\"foo\", []]}")


_json_test_object = {
    "a": "b",
    "x": [1, 2, {}],
    "foo\nbaz\\qux\"\r2": ["bar", 1.2, {"x": "y"}],
    "bar": [True, False, None]
}


class JSONPYON(unittest.TestCase):
    def test_encdec(self):
        for enc in pyon.encode, lambda x: pyon.encode(x, True), json.dumps:
            for dec in pyon.decode, json.loads:
                self.assertEqual(dec(enc(_json_test_object)),
                                 _json_test_object)

    def test_repr(self):
        self.assertEqual(
            pyon.encode(_json_test_object, pretty=False),
            json.dumps(_json_test_object, separators=(",", ":"))
        )
        self.assertEqual(
            pyon.encode(_json_test_object, pretty=True),
            json.dumps(_json_test_object, indent=4)
        )

    def test_transparent(self):
        j = json.loads(pyon.encode(_pyon_test_object))
        p = pyon.decode(json.dumps(j))
        self.assertEqual(_pyon_test_object, p)


class V1(unittest.TestCase):
    def test_decode(self):
        x = {
            (1, 2j): Fraction(4, 1),
        }
        self.assertEqual(x, pyon.decode_v1(str(x)))


class Custom:
    def __init__(self, data):
        self.data = data

    def __eq__(self, other):
        return other.data == self.data


class CustomType(unittest.TestCase):
    def setUp(self):
        pyon.register(
            [Custom], name="custom", encode=lambda x: [pyon.wrap(x.data)], decode=Custom
        )

    def tearDown(self):
        try:
            pyon.deregister([Custom], "custom")
        except:
            pass

    def test_custom(self):
        o = {
            "py": Custom(_pyon_test_object),
            1: (Custom(_json_test_object),),
        }
        self.assertEqual(o, pyon.decode(pyon.encode(o)))

    def test_unique_type(self):
        with self.assertRaises(AssertionError):
            pyon.register(
                [Custom], name="other", encode=lambda: None, decode=lambda: None
            )

    def test_unique_name(self):
        with self.assertRaises(AssertionError):
            pyon.register(
                [None],
                name="custom",
                encode=lambda: None,
                decode=lambda: None,
            )

    def test_common_name(self):
        with self.assertRaises(AssertionError):
            pyon.deregister([Custom, set], "custom")

    def test_not_registered(self):
        with self.assertRaises(KeyError):
            pyon.deregister([None], "other")


class NpScalarTypes(unittest.TestCase):
    def test(self):
        for t in pyon._numpy_scalar:
            if t == "datetime64":
                v = 0, "s"  # otherwise not-a-date
            elif t == "bytes_":
                v = (b"1",)  # numpy doesn't support zero-length bytes
            else:
                v = (0,)
            v = getattr(np, t)(*v)
            with self.subTest(t):
                e = pyon.encode(v)
                d = pyon.decode(e)
                self.assertEqual(d, v)
