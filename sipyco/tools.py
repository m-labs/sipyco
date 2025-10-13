import asyncio
import signal
import socket
import ssl
import atexit
import collections
import logging
from copy import copy

from sipyco import keepalive

logger = logging.getLogger(__name__)


class TaskObject:
    def start(self, *, loop=None):
        """loop must be specified unless this is called from a running event loop."""
        async def log_exceptions(awaitable):
            try:
                return await awaitable()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error("Unhandled exception in TaskObject task body", exc_info=True)
                raise

        self.task = asyncio.ensure_future(log_exceptions(self._do), loop=loop)

    async def stop(self):
        self.task.cancel()
        try:
            await asyncio.wait_for(self.task, None)
        except asyncio.CancelledError:
            pass
        del self.task

    async def _do(self):
        raise NotImplementedError


class BackgroundTaskPool:
    def __init__(self, loop):
        self.loop = loop
        self.tasks = set()

    def create(self, coro):
        # as per https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task
        task = self.loop.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)


class AsyncioServer:
    """Generic TCP server based on asyncio.

    Users of this class must derive from it and define the
    :meth:`~sipyco.asyncio_server.AsyncioServer._handle_connection_cr`
    method/coroutine.
    """
    def __init__(self):
        self._client_tasks = set()

    async def start(self, host, port, ssl_config=None):
        """Starts the server.

        The user must call :meth:`stop`
        to free resources properly after this method completes successfully.

        This method is a *coroutine*.

        :param host: Bind address of the server (see ``asyncio.start_server``
            from the Python standard library).
        :param port: TCP port to bind to.
        :param ssl_config: Optional ``SimpleSSLConfig`` object for secure connections.
            If provided, SSL will be enabled with the specified certificates.
            See :class:`~sipyco.tools.SimpleSSLConfig` for more details.
        """
        ssl_context = None
        if ssl_config is not None:
            ssl_context = ssl_config.create_server_context()
        self.server = await asyncio.start_server(self._handle_connection,
                                                 host, port,
                                                 ssl=ssl_context,
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
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except:
            logger.error("Client connection closed with error", exc_info=True)

    def _handle_connection(self, reader, writer):
        keepalive.set_keepalive(writer.get_extra_info("socket"))
        task = asyncio.ensure_future(self._handle_connection_and_close(reader, writer))
        self._client_tasks.add(task)
        task.add_done_callback(self._client_done)

    async def _handle_connection_and_close(self, reader, writer):
        client_disconnect = False
        try:
            await self._handle_connection_cr(reader, writer)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            client_disconnect = True
        finally:
            writer.close()
            if not client_disconnect:
                await writer.wait_closed()

    async def _handle_connection_cr(self, reader, writer):
        raise NotImplementedError


class Condition:
    def __init__(self, *, loop=None):
        self._waiters = collections.deque()

    async def wait(self):
        """Wait until notified."""
        fut = asyncio.Future(loop=asyncio.get_event_loop())
        self._waiters.append(fut)
        try:
            await fut
        finally:
            self._waiters.remove(fut)

    def notify(self):
        for fut in self._waiters:
            if not fut.done():
                fut.set_result(False)


def atexit_register_coroutine(coroutine, *, loop=None):
    """loop must be specified unless this is called from a running event loop"""
    if loop is None:
        loop = asyncio.get_event_loop()
    atexit.register(lambda: loop.run_until_complete(coroutine()))


HAS_SIGHUP = hasattr(signal, "SIGHUP")


class SignalHandler:
    def setup(self):
        self.prev_sigint = signal.signal(signal.SIGINT, lambda sig, frame: None)
        self.prev_sigterm = signal.signal(signal.SIGTERM, lambda sig, frame: None)
        if HAS_SIGHUP:
            self.prev_sighup = signal.signal(signal.SIGHUP, lambda sig, frame: None)
        self.rsock, self.wsock = socket.socketpair()
        self.rsock.setblocking(0)
        self.wsock.setblocking(0)
        self.prev_wakeup_fd = signal.set_wakeup_fd(self.wsock.fileno())

    def teardown(self):
        signal.set_wakeup_fd(self.prev_wakeup_fd)
        self.rsock.close()
        self.wsock.close()
        signal.signal(signal.SIGINT, self.prev_sigint)
        signal.signal(signal.SIGTERM, self.prev_sigterm)
        if HAS_SIGHUP:
            signal.signal(signal.SIGHUP, self.prev_sighup)

    async def wait_terminate(self):
        loop = asyncio.get_event_loop()
        while True:
            signum = (await loop.sock_recv(self.rsock, 1))[0]
            if signum == signal.SIGINT:
                print()
                print("Caught Ctrl-C, terminating...")
                break
            elif signum == signal.SIGTERM:
                print()
                print("Caught SIGTERM, terminating...")
                break
            elif HAS_SIGHUP and signum == signal.SIGHUP:
                print()
                print("Caught SIGHUP, terminating...")
                break


class SimpleSSLConfig:
    """Handles SSL/TLS context configuration.

    :param local_cert: Local certificate file path.
    :param local_key: Local private key file path.
    :param peer_cert: Peer's certificate file path to trust.
    """
    def __init__(self, local_cert, local_key, peer_cert):
        self.local_cert = local_cert
        self.local_key = local_key
        self.peer_cert = peer_cert

    def create_client_context(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.load_verify_locations(cafile=self.peer_cert)
        context.load_cert_chain(self.local_cert, self.local_key)
        return context

    def create_server_context(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_verify_locations(cafile=self.peer_cert)
        context.load_cert_chain(self.local_cert, self.local_key)
        return context
