import sys
import asyncio
import unittest
import tempfile

from sipyco.pc_rpc import Server
from sipyco.test.ssl_certs import create_ssl_certs, create_ssl_config


class Target:
    def output_value(self):
        return 4125380


class TestRPCTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cert_dir = tempfile.TemporaryDirectory()
        cls.ssl_certs = create_ssl_certs(cls.cert_dir.name)

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    async def check_value(self, ssl=False):
        cmd = [sys.executable, "-m", "sipyco.sipyco_rpctool", "::1", "7777"]
        if ssl:
            cmd.extend(["--ssl", self.ssl_certs["client_cert"],
                                 self.ssl_certs["client_key"],
                                 self.ssl_certs["server_cert"]])
        cmd.extend(["call", "output_value"])

        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE)
        (value, err) = await proc.communicate()
        self.assertEqual(value.decode('ascii').rstrip(), '4125380')
        await proc.wait()

    async def do_test(self, ssl=False):
        ssl_config = create_ssl_config("server", self.ssl_certs) if ssl else None
        server = Server({"target": Target()})
        await server.start("::1", 7777, ssl_config)
        await self.check_value(ssl)
        await server.stop()

    def test_rpc(self):
        self.loop.run_until_complete(self.do_test())

    def test_rpc_ssl(self):
        self.loop.run_until_complete(self.do_test(ssl=True))

    @classmethod
    def tearDownClass(cls):
        cls.cert_dir.cleanup()

    def tearDown(self):
        self.loop.close()
