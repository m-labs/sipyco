import asyncio
import inspect
import subprocess
import sys
import time
import unittest
import ssl
import tempfile
import argparse

import numpy as np

from sipyco import pc_rpc, pyon
from sipyco.tools import SimpleSSLConfig
from sipyco.test.ssl_certs import create_ssl_certs, create_ssl_config


test_address = "::1"
test_port = 7777
test_object = [5, 2.1, None, True, False,
               {"a": 5, 2: np.linspace(0, 10, 1)},
               (4, 5), (10,), "ab\nx\"'"]


class RPCCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cert_dir = tempfile.TemporaryDirectory()
        cls.ssl_certs = create_ssl_certs(cls.cert_dir.name)

    def _run_server_and_test(self, test, *args, ssl_config=None):
        cmd_args = [sys.executable, sys.modules[__name__].__file__]
        if ssl_config is not None:
            cmd_args.extend(["--ssl", self.ssl_certs["server_cert"],
                                      self.ssl_certs["server_key"],
                                      self.ssl_certs["client_cert"]])

        # running this file outside of unittest starts the echo server
        with subprocess.Popen(cmd_args) as proc:
            try:
                test(*args, ssl_config=ssl_config)
            finally:
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    proc.kill()

    def _blocking_echo(self, target, die_using_sys_exit=False, ssl_config=None):
        for attempt in range(100):
            time.sleep(.2)
            try:
                remote = pc_rpc.Client(test_address, test_port, target, ssl_config=ssl_config)
            except ConnectionRefusedError:
                pass
            else:
                break
        try:
            test_object_back = remote.echo(test_object)
            self.assertEqual(test_object, test_object_back)
            test_object_back = remote.async_echo(test_object)
            self.assertEqual(test_object, test_object_back)
            with self.assertRaises(TypeError):
                remote.return_unserializable()
            with self.assertRaises(AttributeError):
                remote.non_existing_method
            if die_using_sys_exit:
                # If the server dies and just drops the connection, we
                # expect a client-side error due to lack of data.
                with self.assertRaises(EOFError):
                    remote.raise_sys_exit()
            else:
                remote.terminate()
        finally:
            remote.close_rpc()

    def test_blocking_echo(self):
        self._run_server_and_test(self._blocking_echo, "test")

    def test_blocking_echo_ssl(self):
        ssl_config = create_ssl_config("client", self.ssl_certs)
        self._run_server_and_test(self._blocking_echo, "test", ssl_config)

    def _test_ssl_invalid_certs(self, echo_func):
        with tempfile.TemporaryDirectory() as wrong_cert_dir:
            wrong_certs = create_ssl_certs(wrong_cert_dir)
            wrong_client_config = SimpleSSLConfig(wrong_certs["client_cert"],
                                                  wrong_certs["client_key"],
                                                  self.ssl_certs["server_cert"])

            wrong_key_config = SimpleSSLConfig(self.ssl_certs["client_cert"],
                                               wrong_certs["client_key"],
                                               self.ssl_certs["server_cert"])

            wrong_peer_config = SimpleSSLConfig(self.ssl_certs["client_cert"],
                                                self.ssl_certs["client_key"],
                                                wrong_certs["server_cert"])

            with self.assertRaises((EOFError, BrokenPipeError, ConnectionResetError)):
                    self._run_server_and_test(echo_func, "test", ssl_config=wrong_client_config)

            with self.assertRaises(ssl.SSLError):
                    self._run_server_and_test(echo_func, "test", ssl_config=wrong_key_config)

            with self.assertRaises(ssl.SSLCertVerificationError):
                    self._run_server_and_test(echo_func, "test", ssl_config=wrong_peer_config)

    def test_blocking_echo_ssl_invalid_certs(self):
        self._test_ssl_invalid_certs(self._blocking_echo)

    def test_sys_exit(self):
        self._run_server_and_test(self._blocking_echo, "test", True)

    def test_blocking_echo_autotarget(self):
        self._run_server_and_test(self._blocking_echo, pc_rpc.AutoTarget)

    async def _asyncio_echo(self, target, ssl_config=None):
        remote = pc_rpc.AsyncioClient()
        for attempt in range(100):
            await asyncio.sleep(.2)
            try:
                await remote.connect_rpc(test_address, test_port, target, ssl_config)
            except ConnectionRefusedError:
                pass
            else:
                break
        try:
            test_object_back = await remote.echo(test_object)
            self.assertEqual(test_object, test_object_back)
            test_object_back = await remote.async_echo(test_object)
            self.assertEqual(test_object, test_object_back)
            with self.assertRaises(TypeError):
                await remote.return_unserializable()
            with self.assertRaises(AttributeError):
                await remote.non_existing_method
            await remote.terminate()
        finally:
            await remote.close_rpc()

    def _loop_asyncio_echo(self, target, ssl_config=None):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._asyncio_echo(target, ssl_config))
        finally:
            loop.close()

    def test_asyncio_echo(self):
        self._run_server_and_test(self._loop_asyncio_echo, "test")

    def test_asyncio_echo_ssl(self):
        ssl_config = create_ssl_config("client", self.ssl_certs)
        self._run_server_and_test(self._loop_asyncio_echo, "test", ssl_config=ssl_config)

    def test_asyncio_echo_ssl_invalid_certs(self):
        self._test_ssl_invalid_certs(self._loop_asyncio_echo)

    def test_asyncio_echo_autotarget(self):
        self._run_server_and_test(self._loop_asyncio_echo, pc_rpc.AutoTarget)

    def test_rpc_encode_function(self):
        """Test that `pc_rpc` can encode a function properly.

        Used in `get_rpc_method_list` part of
        :meth:`sipyco.pc_rpc.Server._process_action`
        """

        def _annotated_function(
            arg1: str, arg2: np.ndarray = np.array([1,])
        ) -> np.ndarray:
            """Sample docstring."""
            return arg1

        argspec_documented, docstring = pc_rpc.Server._document_function(
            _annotated_function
        )
        self.assertEqual(docstring, "Sample docstring.")

        # purposefully ignore how argspec["annotations"] is treated.
        # allows option to change PYON later to encode annotations.
        argspec_master = dict(inspect.getfullargspec(_annotated_function)._asdict())
        argspec_without_annotation = argspec_master.copy()
        del argspec_without_annotation["annotations"]
        # check if all items (excluding annotations) are same in both dictionaries
        self.assertLessEqual(
            argspec_without_annotation.items(), argspec_documented.items()
        )
        self.assertDictEqual(
            argspec_documented, pyon.decode(pyon.encode(argspec_documented))
        )

    @classmethod
    def tearDownClass(cls):
        cls.cert_dir.cleanup()

class Echo:
    def raise_sys_exit(self):
        sys.exit(0)

    def echo(self, x):
        return x

    async def async_echo(self, x):
        await asyncio.sleep(0.01)
        return x

    def return_unserializable(self):
        # Arbitrary classes can't be PYON-serialized.
        return Echo()


def run_server():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ssl", nargs=3, metavar=("CERT", "KEY", "PEER"))
    args = parser.parse_args()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        echo = Echo()
        server = pc_rpc.Server({"test": echo}, builtin_terminate=True)
        ssl_config = SimpleSSLConfig(*args.ssl) if args.ssl else None
        loop.run_until_complete(server.start(test_address, test_port, ssl_config))
        try:
            loop.run_until_complete(server.wait_terminate())
        finally:
            loop.run_until_complete(server.stop())
    finally:
        loop.close()


if __name__ == "__main__":
    run_server()
