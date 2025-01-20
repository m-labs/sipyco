import asyncio
import logging
import unittest
import tempfile

from sipyco import logs
from sipyco.test.ssl_certs import create_ssl_certs, create_ssl_config


test_address = "::1"
test_port = 7777
test_messages = [
    ("This is a debug message", logging.DEBUG),
    ("This is an info message", logging.INFO),
    ("This is a warning message", logging.WARNING),
    ("This is an error message", logging.ERROR),
    ("This is a multi-line message\nwith two\nlines", logging.INFO)]


class LoggingCase(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.cert_dir = None

        self.client_logger = logging.getLogger("client_logger")
        self.client_logger.setLevel(logging.DEBUG)

        self.fwd_logger = logs._fwd_logger
        self.fwd_logger.setLevel(logging.DEBUG)

        self.received_records = []
        self.received_records_sem = asyncio.Semaphore(0)

        self.handler = logging.StreamHandler()
        self.handler.setFormatter(logs.MultilineFormatter())
        self.handler.emit = self.handle_record
        self.fwd_logger.addHandler(self.handler)

    def handle_record(self, record):
        self.received_records.append(record)
        self.received_records_sem.release()

    async def _do_test_logging(self, ssl=False):
        server_config = None
        client_config = None
        if ssl:
            self.cert_dir = tempfile.TemporaryDirectory()
            certs = create_ssl_certs(self.cert_dir.name)
            server_config = create_ssl_config("server", certs)
            client_config = create_ssl_config("client", certs)

        server = logs.Server()
        await server.start(test_address, test_port, server_config)

        try:
            forwarder = logs.LogForwarder(
                test_address, test_port, reconnect_timer=0.1, ssl_config=client_config)
            forwarder.setFormatter(logs.MultilineFormatter())

            self.client_logger.addFilter(
                logs.SourceFilter(logging.DEBUG, "test_client"))
            self.client_logger.addHandler(forwarder)

            forwarder_task = asyncio.create_task(forwarder._do())

            try:
                for message, level in test_messages:
                    self.received_records.clear()
                    self.client_logger.log(level, message)
                    await self.received_records_sem.acquire()

                    self.assertTrue(self.received_records)
                    record = self.received_records[0]
                    self.assertEqual(record.getMessage(), message)
                    self.assertEqual(record.levelno, level)
                    self.assertEqual(record.source, "test_client")
            finally:
                self.client_logger.removeHandler(forwarder)
                forwarder_task.cancel()
                try:
                    await forwarder_task
                except asyncio.CancelledError:
                    pass
        finally:
            await server.stop()

    def test_logging(self):
        self.loop.run_until_complete(self._do_test_logging())

    def test_logging_ssl(self):
        self.loop.run_until_complete(self._do_test_logging(ssl=True))

    def tearDown(self):
        if self.cert_dir is not None:
            self.cert_dir.cleanup()
        self.fwd_logger.removeHandler(self.handler)
        self.loop.close()
