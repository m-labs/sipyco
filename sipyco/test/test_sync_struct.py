import unittest
import asyncio
import tempfile
import numpy as np

from sipyco import sync_struct
from sipyco.test.ssl_certs import create_ssl_certs, create_ssl_config


test_address = "::1"
test_port = 7777


def write_test_data(test_dict):
    test_values = [5, 2.1, None, True, False,
                   {"a": 5, 2: np.linspace(0, 10, 1)},
                   (4, 5), (10,), "ab\nx\"'"]
    for i in range(10):
        test_dict[str(i)] = i
    for key, value in enumerate(test_values):
        test_dict[key] = value
    test_dict[1.5] = 1.5
    test_dict["list"] = []
    test_dict["list"][:] = [34, 31]
    test_dict["list"].append(42)
    test_dict["list"].insert(1, 1)
    test_dict[100] = 0
    test_dict[100] = 1
    test_dict[101] = 1
    test_dict.pop(101)
    test_dict[102] = 1
    del test_dict[102]
    test_dict["array"] = np.zeros(1)
    test_dict["array"][0] = 10
    test_dict["finished"] = True


class SyncStructCase(unittest.TestCase):
    def init_test_dict(self, init):
        self.received_dict = init
        self.init_done.set()
        return init

    def notify(self, mod):
        if ((mod["action"] == "init" and "finished" in mod["struct"])
                or (mod["action"] == "setitem" and mod["key"] == "finished")):
            self.receiving_done.set()

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.cert_dir = None

    async def _do_test_recv(self, ssl=False):
        self.init_done = asyncio.Event()
        self.receiving_done = asyncio.Event()

        server_config = None
        client_config = None
        if ssl:
            self.cert_dir = tempfile.TemporaryDirectory()
            certs = create_ssl_certs(self.cert_dir.name)
            server_config = create_ssl_config("server", certs)
            client_config = create_ssl_config("client", certs)

        test_dict = sync_struct.Notifier(dict())
        publisher = sync_struct.Publisher({"test": test_dict})

        await publisher.start(test_address, test_port, server_config)

        subscriber = sync_struct.Subscriber("test", self.init_test_dict,
                                            self.notify)
        await subscriber.connect(test_address, test_port, None, client_config)

        # Wait for the initial replication to be completed so we actually
        # exercise the various actions instead of sending just one init mod.
        await self.init_done.wait()

        write_test_data(test_dict)
        await self.receiving_done.wait()

        await subscriber.close()
        await publisher.stop()

        self.assertEqual(self.received_dict, test_dict.raw_view)

    def test_recv(self):
        self.loop.run_until_complete(self._do_test_recv())

    def test_recv_ssl(self):
        self.loop.run_until_complete(self._do_test_recv(ssl=True))

    def tearDown(self):
        if self.cert_dir is not None:
            self.cert_dir.cleanup()
        self.loop.close()
