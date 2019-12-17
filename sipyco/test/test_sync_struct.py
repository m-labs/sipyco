import unittest
import asyncio
import numpy as np

from sipyco import sync_struct


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

    def init_test_dict2(self, init):
        self.received_dict2 = init
        self.receiving_done2.set()
        return init

    def notify(self, mod):
        if ((mod["action"] == "init" and "finished" in mod["struct"])
                or (mod["action"] == "setitem" and mod["key"] == "finished")):
            self.receiving_done.set()

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    async def _do_test_recv(self):
        # Test sending/receiving changes after a client has already connected.

        self.init_done = asyncio.Event()
        self.receiving_done = asyncio.Event()

        test_dict = sync_struct.Notifier(dict())
        publisher = sync_struct.Publisher({"test": test_dict})
        await publisher.start(test_address, test_port)

        subscriber = sync_struct.Subscriber("test", self.init_test_dict,
                                            self.notify)
        await subscriber.connect(test_address, test_port)

        # Wait for the initial replication to be completed so we actually
        # exercise the various actions instead of sending just one init mod.
        await self.init_done.wait()

        write_test_data(test_dict)
        await self.receiving_done.wait()

        self.assertEqual(self.received_dict, test_dict.raw_view)


        # Test adding a notifier and initialising a client from existing data.

        self.receiving_done2 = asyncio.Event()

        publisher.add_notifier("test2", test_dict)
        subscriber2 = sync_struct.Subscriber("test", self.init_test_dict2,
                                             None)
        await subscriber2.connect(test_address, test_port)
        await self.receiving_done2.wait()

        self.assertEqual(self.received_dict2, test_dict.raw_view)

        await subscriber2.close()
        await subscriber.close()
        await publisher.stop()

    def test_recv(self):
        self.loop.run_until_complete(self._do_test_recv())

    def tearDown(self):
        self.loop.close()


class RemoveNotifierCase(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def init_test_dict(self, init):
        self.received_dict = init
        self.init_done.set()
        return init

    def set_done(self):
        self.subscriber_done.set()

    async def _do_test_recv(self):
        self.init_done = asyncio.Event()
        self.subscriber_done = asyncio.Event()

        notifier = sync_struct.Notifier(dict())
        publisher = sync_struct.Publisher({"test": notifier})
        await publisher.start(test_address, test_port)

        subscriber = sync_struct.Subscriber("test", self.init_test_dict,
                                            disconnect_cb=self.set_done)
        await subscriber.connect(test_address, test_port)

        await self.init_done.wait()
        notifier["test_data"] = 42
        publisher.remove_notifier("test")

        await self.subscriber_done.wait()
        self.assertEqual(self.received_dict, notifier.raw_view)

        await publisher.stop()

    def test_recv(self):
        self.loop.run_until_complete(self._do_test_recv())

    def tearDown(self):
        self.loop.close()
