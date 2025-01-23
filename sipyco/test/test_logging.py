import asyncio
import logging
import unittest

from sipyco import logging_tools


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

        self.client_logger = logging.getLogger("client_logger")
        self.client_logger.setLevel(logging.DEBUG)

        self.fwd_logger = logging_tools._fwd_logger
        self.fwd_logger.setLevel(logging.DEBUG)

        self.received_records = []
        self.received_records_sem = asyncio.Semaphore(0)

        self.handler = logging.StreamHandler()
        self.handler.setFormatter(logging_tools.MultilineFormatter())
        self.handler.emit = self.handle_record
        self.fwd_logger.addHandler(self.handler)

    def handle_record(self, record):
        self.received_records.append(record)
        self.received_records_sem.release()

    async def _do_test_logging(self):
        server = logging_tools.Server()
        await server.start(test_address, test_port)

        try:
            forwarder = logging_tools.LogForwarder(
                test_address, test_port, reconnect_timer=0.1)
            forwarder.setFormatter(logging_tools.MultilineFormatter())

            self.client_logger.addFilter(
                logging_tools.SourceFilter(logging.DEBUG, "test_client"))
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

    def tearDown(self):
        self.fwd_logger.removeHandler(self.handler)
        self.loop.close()
