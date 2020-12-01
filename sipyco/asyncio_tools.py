import asyncio
import atexit
import collections
import logging
from copy import copy

logger = logging.getLogger(__name__)


class TaskObject:
    def start(self):
        async def log_exceptions(awaitable):
            try:
                return await awaitable()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error("Unhandled exception in TaskObject task body", exc_info=True)
                raise

        self.task = asyncio.ensure_future(log_exceptions(self._do))

    async def stop(self):
        self.task.cancel()
        try:
            await asyncio.wait_for(self.task, None)
        except asyncio.CancelledError:
            pass
        del self.task

    async def _do(self):
        raise NotImplementedError


class AsyncioServer:
    """Generic TCP server based on asyncio.

    Users of this class must derive from it and define the
    :meth:`~sipyco.asyncio_server.AsyncioServer._handle_connection_cr`
    method/coroutine.
    """
    def __init__(self):
        self._client_tasks = set()

    async def start(self, host, port):
        """Starts the server.

        The user must call :meth:`stop`
        to free resources properly after this method completes successfully.

        This method is a *coroutine*.

        :param host: Bind address of the server (see ``asyncio.start_server``
            from the Python standard library).
        :param port: TCP port to bind to.
        """
        self.server = await asyncio.start_server(self._handle_connection,
                                                 host, port,
                                                 limit=4*1024*1024)

    async def stop(self):
        """Stops the server."""
        wait_for = copy(self._client_tasks)
        for task in self._client_tasks:
            task.cancel()
        for task in wait_for:
            try:
                await asyncio.wait_for(task, None)
            except asyncio.CancelledError:
                pass
        self.server.close()
        await self.server.wait_closed()
        del self.server

    def _client_done(self, task):
        self._client_tasks.remove(task)
        if not task.cancelled() and task.exception():
            logger.error("Client connection closed with error", exc_info=True)

    def _handle_connection(self, reader, writer):
        task = asyncio.ensure_future(self._handle_connection_cr(reader, writer))
        self._client_tasks.add(task)
        task.add_done_callback(self._client_done)

    async def _handle_connection_cr(self, reader, writer):
        raise NotImplementedError


class Condition:
    def __init__(self, *, loop=None):
        if loop is not None:
            self._loop = loop
        else:
            self._loop = asyncio.get_event_loop()
        self._waiters = collections.deque()

    async def wait(self):
        """Wait until notified."""
        fut = asyncio.Future(loop=self._loop)
        self._waiters.append(fut)
        try:
            await fut
        finally:
            self._waiters.remove(fut)

    def notify(self):
        for fut in self._waiters:
            if not fut.done():
                fut.set_result(False)


def atexit_register_coroutine(coroutine, loop=None):
    if loop is None:
        loop = asyncio.get_event_loop()
    atexit.register(lambda: loop.run_until_complete(coroutine()))
