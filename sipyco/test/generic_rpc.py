import unittest
import subprocess
import shlex
import time
import socket

from sipyco.pc_rpc import AutoTarget, Client


class GenericRPCCase(unittest.TestCase):
    def setUp(self):
        self.servers = {}

    def tearDown(self):
        for name in list(self.servers):
            self.stop_server(name)

    def start_server(self, name, command, port, sleep=2, target_name=AutoTarget, timeout=1):
        if name in self.servers:
            raise ValueError("server `{}` already started".format(name))
        proc = subprocess.Popen(shlex.split(command))
        time.sleep(sleep)
        client = Client("localhost", port, target_name, timeout)
        self.servers[name] = proc, port, client
        return client

    def stop_server(self, name, timeout=1):
        proc, port, client = self.servers[name]
        try:
            try:
                client.terminate()
                client.close_rpc()
                proc.wait(timeout)
                return
            except (socket.timeout, subprocess.TimeoutExpired):
                logger.warning("Server %s failed to exit on request", name)
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout)
                return
            except subprocess.TimeoutExpired:
                logger.warning("Server %s failed to exit on terminate",
                               name)
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout)
                return
            except subprocess.TimeoutExpired:
                logger.warning("Server %s failed to die on kill", name)
        finally:
            del self.servers[name]

