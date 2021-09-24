import os
import sys
import asyncio
import unittest

from typing import Dict, Optional, List, Any

from sipyco.pc_rpc import Server
from unittest import IsolatedAsyncioTestCase


class Target:
    def output_value(self) -> None:
        """
        This is a docstring
        """
        return 4125380

    def plus(self, a: int, b: int = 0) -> int:
        """
        Calculates a + b
        :param a: left operand
        :param b: right operand
        :return: the sum of a and b
        """
        return a + b

    def max(self, a: int, b: int) -> 'Optional[int]':
        """
        Compares a and b, and find which one is bigger
        :param a: left comparator
        :param b: right comparator
        :return: the larger number, if both are the same, none
        """
        return None if a == b else max(a, b)

    def dictify(self, args: 'List[Any]') -> 'Dict[Any, Any]':
        if len(args) % 2 == 1:
            raise ArithmeticError("not pairs")

        return dict([(args[i], args[i + 1]) for i in range(0, len(args), 2)])

    def identity(self, x) -> Any:
        return x


# ensure the methods are sorted
list_method_fixture = """
dictify(args: 'List[Any]') -> 'Dict[Any, Any]'

identity(x) -> Any

max(a: int, b: int) -> 'Optional[int]'
    Compares a and b, and find which one is bigger
    :param a: left comparator
    :param b: right comparator
    :return: the larger number, if both are the same, none

output_value() -> None
    This is a docstring

plus(a: int, b: int = 0) -> int
    Calculates a + b
    :param a: left operand
    :param b: right operand
    :return: the sum of a and b

terminate()
    Terminate the server.
""".strip()


class TestRPCTool(IsolatedAsyncioTestCase):
    async def run_server_command(self, *commands):
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "sipyco.sipyco_rpctool", "::1", "7777", *commands,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            value, err = await proc.communicate()
            if err:
                raise RuntimeError(err)
            return value
        finally:
            if proc:
                await proc.wait()

    async def test_call(self):
        value = await self.run_server_command("call", "output_value")
        self.assertEqual(value.decode('ascii').rstrip(), '4125380')

        value = await self.run_server_command("call", "dictify", """["a", "b", "c", "d"]""")
        self.assertEqual(value.decode('ascii').rstrip(), """{'a': 'b', 'c': 'd'}""")

        with self.assertRaises(RuntimeError):
            await self.run_server_command("call", "dictify", """["a", "b", "c"]""")

    async def test_list_method(self):
        value = await self.run_server_command("list-methods")
        self.assertEqual(value.decode('ascii').strip(), list_method_fixture)

    async def asyncSetUp(self):
        self.maxDiff = None
        self.server = Server({"target": Target()}, builtin_terminate=True)
        await self.server.start("::1", 7777)

    async def asyncTearDown(self) -> None:
        await self.server.stop()
