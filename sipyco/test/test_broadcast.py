import unittest
import asyncio
import tempfile

from sipyco import broadcast
from sipyco.test.ssl_certs import create_ssl_certs, create_ssl_config


test_address = "::1"
test_port = 7777
test_message = {"key": "value", "number": 42}


class BroadcastCase(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.message_received = asyncio.Event()
        self.cert_dir = None

    async def _do_test_broadcast(self, ssl=False):
        received_messages = []

        def notify_callback(message):
            received_messages.append(message)
            self.message_received.set()

        server_config = None
        client_config = None
        if ssl:
            self.cert_dir = tempfile.TemporaryDirectory()
            certs = create_ssl_certs(self.cert_dir.name)
            server_config = create_ssl_config("server", certs)
            client_config = create_ssl_config("client", certs)

        broadcaster = broadcast.Broadcaster()
        await broadcaster.start(test_address, test_port, server_config)

        receiver = broadcast.Receiver("test_channel", notify_callback)
        await receiver.connect(test_address, test_port, client_config)

        # Sleep to avoid race condition. If broadcast() runs before server
        # setup recipient's message queue, initial messages may be lost.
        await asyncio.sleep(0.1)

        broadcaster.broadcast("test_channel", test_message)
        await self.message_received.wait()

        await receiver.close()
        await broadcaster.stop()

        self.assertEqual(len(received_messages), 1)
        self.assertEqual(received_messages, [test_message])

    def test_broadcast(self):
        self.loop.run_until_complete(self._do_test_broadcast())

    def test_broadcast_ssl(self):
        self.loop.run_until_complete(self._do_test_broadcast(ssl=True))

    def tearDown(self):
        if self.cert_dir is not None:
            self.cert_dir.cleanup()
        self.loop.close()
