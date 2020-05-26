"""
This module provides a remote procedure call (RPC) mechanism over sockets
between conventional computers (PCs) running Python. It strives to be
transparent and uses :mod:`sipyco.pyon` internally so that e.g. Numpy
arrays can be easily used.

Note that the server operates on copies of objects provided by the client,
and modifications to mutable types are not written back. For example, if the
client passes a list as a parameter of an RPC method, and that method
``append()s`` an element to the list, the element is not appended to the
client's list.
"""

import asyncio
import inspect
import logging
import socket
import threading
import time
from operator import itemgetter

from sipyco.monkey_patches import *
from sipyco import pyon
from sipyco.asyncio_tools import AsyncioServer as _AsyncioServer
from sipyco.packed_exceptions import current_exc_packed, raise_packed_exc

logger = logging.getLogger(__name__)


class AutoTarget:
    """Use this as target value in clients for them to automatically connect
    to the target exposed by the server. Servers must have only one target."""
    pass


class IncompatibleServer(Exception):
    """Raised by the client when attempting to connect to a server that does
    not have the expected target."""
    pass


class RPCConnectionError(ConnectionError):
    """Raised by the client when a method called fails due to connection
    problems with the RPC server.
    """
    pass


_init_string = b"ARTIQ pc_rpc\n"


def _validate_target_name(target_name, target_names):
    if target_name is AutoTarget:
        if len(target_names) > 1:
            raise ValueError("Server has multiple targets: " +
                             " ".join(sorted(target_names)))
        else:
            target_name = target_names[0]
    elif target_name not in target_names:
        raise IncompatibleServer(
            "valid target name(s): " + " ".join(sorted(target_names)))
    return target_name


class Client:
    """This class proxies the methods available on the server so that they
    can be used as if they were local methods.

    For example, if the server provides method ``foo``, and ``c`` is a local
    :class:`.Client` object, then the method can be called as: ::

        result = c.foo(param1, param2)

    The parameters and the result are automatically transferred from the
    server.

    Only methods are supported. Attributes must be accessed by providing and
    using "get" and/or "set" methods on the server side.

    At object initialization, the connection to the remote server is
    automatically attempted. The user must call :meth:`~sipyco.pc_rpc.Client.close_rpc` to
    free resources properly after initialization completes successfully.

    If the remote server shuts down during operation, RPCConnectionError is
    raised by future calls to Client methods. The user should call
    :meth:`~sipyco.pc_rpc.Client.close_rpc` and then discard this object.

    :param host: Identifier of the server. The string can represent a
        hostname or a IPv4 or IPv6 address (see
        ``socket.create_connection`` in the Python standard library).
    :param port: TCP port to use.
    :param target_name: Target name to select. ``IncompatibleServer`` is
        raised if the target does not exist.
        Use :class:`.AutoTarget` for automatic selection if the server has 
        only one target.
        Use ``None`` to skip selecting a target. The list of targets can then
        be retrieved using :meth:`~sipyco.pc_rpc.Client.get_rpc_id`
        and then one can be selected later using :meth:`~sipyco.pc_rpc.Client.select_rpc_target`.
    :param timeout: Socket operation timeout. Use ``None`` for blocking
        (default), ``0`` for non-blocking, and a finite value to raise
        ``socket.timeout`` if an operation does not complete within the
        given time. See also ``socket.create_connection()`` and
        ``socket.settimeout()`` in the Python standard library. A timeout
        in the middle of a RPC can break subsequent RPCs (from the same
        client).
    """
    def __init__(self, host, port, target_name=AutoTarget, timeout=None):
        self.__socket = socket.create_connection((host, port), timeout)

        self.__closed = False

        try:
            self.__socket.sendall(_init_string)

            server_identification = self.__recv()
            self.__target_names = server_identification["targets"]
            self.__description = server_identification["description"]
            self.__selected_target = None
            self.__valid_methods = set()
            if target_name is not None:
                self.select_rpc_target(target_name)
        except:
            self.__socket.close()
            raise

    def select_rpc_target(self, target_name):
        """Selects a RPC target by name. This function should be called
        exactly once if the object was created with ``target_name=None``."""
        target_name = _validate_target_name(target_name, self.__target_names)
        self.__socket.sendall((target_name + "\n").encode())
        self.__selected_target = target_name
        self.__valid_methods = self.__recv()

    def get_selected_target(self):
        """Returns the selected target, or ``None`` if no target has been
        selected yet."""
        return self.__selected_target

    def get_rpc_id(self):
        """Returns a tuple (target_names, description) containing the
        identification information of the server."""
        return (self.__target_names, self.__description)

    def get_local_host(self):
        """Returns the address of the local end of the connection."""
        return self.__socket.getsockname()[0]

    def get_valid_methods(self):
        """Returns a set of names of methods which can be called on
        the server"""
        return self.__valid_methods.copy()

    def is_closed(self):
        """Return True if the connection to the server has been closed

        This method will actively query the server for data to check
        if the connection is working. """
        self.__closed = not self.__socket_is_open()

        return self.__closed

    def close_rpc(self):
        """Closes the connection to the RPC server.

        No further method calls should be done after this method is called.
        """
        self.__closed = True
        self.__socket.close()

    def __socket_is_open(self):
        # Consensus seems to be that there's no reliable way to check a socket
        # for disconnection without writing to it / receiving from it. We'll
        # use the "get_rpc_method" action as a test of the connection since all
        # Servers are guaranteed to have it available
        if self.__closed:
            return False

        try:
            self.get_rpc_method_list()
        except socket.error:
            return False
        else:
            return True

    def __send(self, obj):
        line = pyon.encode(obj) + "\n"
        self.__socket.sendall(line.encode())

    def __recv(self):
        if not self.__closed:
            buf = self.__socket.recv(4096).decode()
            while "\n" not in buf:
                more = self.__socket.recv(4096)
                if not more:
                    break
                buf += more.decode()
        if self.__closed or not buf:
            self.__closed = True
            raise RPCConnectionError("Connection closed by server")
        return pyon.decode(buf)

    def __do_action(self, action):
        try:
            self.__send(action)
            obj = self.__recv()
        except ConnectionError as e:
            if isinstance(e, RPCConnectionError):
                raise e
            else:
                raise RPCConnectionError("Failure in RPC comms")

        if obj["status"] == "ok":
            return obj["ret"]
        elif obj["status"] == "failed":
            raise_packed_exc(obj["exception"])
        else:
            raise ValueError

    def __do_rpc(self, name, args, kwargs):
        obj = {"action": "call", "name": name, "args": args, "kwargs": kwargs}
        return self.__do_action(obj)

    def get_rpc_method_list(self):
        obj = {"action": "get_rpc_method_list"}
        return self.__do_action(obj)

    def __getattr__(self, name):
        if name not in self.__valid_methods:
            raise AttributeError("{} not found".format(name))

        def proxy(*args, **kwargs):
            return self.__do_rpc(name, args, kwargs)
        return proxy


class AsyncioClient:
    """This class is similar to :class:`sipyco.pc_rpc.Client`, but
    uses ``asyncio`` instead of blocking calls.

    All RPC methods are coroutines. As with :class:`sipyco.pc_rpc.Client`,
    methods will raise RPCConnectionError if the server closes the
    connection. The user should call
    :meth:`~sipyco.pc_rpc.AsyncioClient.close_rpc` and then discard this
    object.

    Concurrent access from different asyncio tasks is supported; all calls
    use a single lock.
    """
    def __init__(self):
        self.__lock = asyncio.Lock()
        self.__reader = None
        self.__writer = None
        self.__target_names = None
        self.__description = None
        self.__closed = False

    async def connect_rpc(self, host, port, target_name):
        """Connects to the server. This cannot be done in __init__ because
        this method is a coroutine. See :class:`sipyco.pc_rpc.Client` for a
        description of the parameters."""
        self.__reader, self.__writer = \
            await asyncio.open_connection(host, port, limit=100*1024*1024)
        try:
            self.__writer.write(_init_string)
            server_identification = await self.__recv()
            self.__target_names = server_identification["targets"]
            self.__description = server_identification["description"]
            self.__selected_target = None
            self.__valid_methods = set()
            if target_name is not None:
                await self.select_rpc_target(target_name)
        except:
            self.close_rpc()
            raise

    async def select_rpc_target(self, target_name):
        """Selects a RPC target by name. This function should be called
        exactly once if the connection was created with ``target_name=None``.
        """
        target_name = _validate_target_name(target_name, self.__target_names)
        self.__writer.write((target_name + "\n").encode())
        self.__selected_target = target_name
        self.__valid_methods = await self.__recv()

    def get_selected_target(self):
        """Returns the selected target, or ``None`` if no target has been
        selected yet."""
        return self.__selected_target

    async def is_closed(self):
        """Return True if the connection to the server has been closed"""
        self.__closed = not await self.__socket_is_open()

        return self.__closed

    async def get_rpc_method_list(self):
        obj = {"action": "get_rpc_method_list"}
        return await self.__do_action(obj)

    async def __socket_is_open(self):
        # Consensus seems to be that there's no reliable way to check a socket
        # for disconnection without writing to it / receiving from it. We'll
        # use the "get_rpc_method" action as a test of the connection since all
        # Servers are guaranteed to have it available
        if self.__closed:
            return False

        try:
            await self.get_rpc_method_list()
        except socket.error:
            return False
        else:
            return True

    def get_local_host(self):
        """Returns the address of the local end of the connection."""
        return self.__writer.get_extra_info("socket").getsockname()[0]

    def get_rpc_id(self):
        """Returns a tuple (target_names, description) containing the
        identification information of the server."""
        return (self.__target_names, self.__description)

    def close_rpc(self):
        """Closes the connection to the RPC server.

        No further method calls should be done after this method is called.
        """
        if self.__writer is not None:
            self.__writer.close()
        self.__reader = None
        self.__writer = None
        self.__target_names = None
        self.__description = None

    def __send(self, obj):
        line = pyon.encode(obj) + "\n"
        self.__writer.write(line.encode())

    async def __recv(self):
        if not self.__closed:
            line = await self.__reader.readline()
        if self.__closed or not line:
            self.__closed = True
            raise RPCConnectionError("Connection closed by server")
        return pyon.decode(line.decode())

    async def __do_action(self, obj):
        await self.__lock.acquire()
        try:
            self.__send(obj)

            obj = await self.__recv()
            if obj["status"] == "ok":
                return obj["ret"]
            elif obj["status"] == "failed":
                raise_packed_exc(obj["exception"])
            else:
                raise ValueError
        finally:
            self.__lock.release()

    async def __do_rpc(self, name, args, kwargs):
        obj = {"action": "call", "name": name, "args": args, "kwargs": kwargs}
        return await self.__do_action(obj)

    def __getattr__(self, name):
        if name not in self.__valid_methods:
            raise AttributeError("{} not found".format(name))

        async def proxy(*args, **kwargs):
            res = await self.__do_rpc(name, args, kwargs)
            return res
        return proxy


class BestEffortClient:
    """This class is similar to :class:`sipyco.pc_rpc.Client`, but
    network errors are suppressed and connections are retried in the
    background.

    RPC calls that failed because of network errors return ``None``. Other RPC
    calls are blocking and return the correct value.

    This class will launch a Thread which monitors for a failed connection in
    background. If this occurs the connection will be reopened if possible.

    :param firstcon_timeout: Timeout to use during the first (blocking)
        connection attempt at object initialization.
    :param retry: Amount of time to wait between background connectivity
        checks / attempts to reconnect.
    """

    def __init__(self, host, port, target_name,
                 firstcon_timeout=1.0, retry=5.0):
        self.__host = host
        self.__port = port
        self.__target_name = target_name
        self.__retry = retry

        self.__conmonitor_terminate = False
        self.__valid_methods = set()
        self.__client = None  # type: Client
        self.__client_lock = threading.RLock()

        try:
            self.__coninit(firstcon_timeout)
        except ConnectionError:
            logger.warning("first connection attempt to %s:%d[%s] failed, "
                           "retrying in the background",
                           self.__host, self.__port, self.__target_name,
                           exc_info=True)

        self.__start_conmonitor()

    def __coninit(self, timeout):
        try:
            self.__client = Client(self.__host, self.__port,
                                   self.__target_name, timeout)
        except:  # noqa
            self.__client = None
            raise
        else:
            # Get the valid methods so we can check if an attribute exists
            # even if the client is later deleted due to connection error
            self.__valid_methods = self.__client.get_valid_methods()

    def __start_conmonitor(self):
        self.__conmonitor_thread = threading.Thread(target=self.__conmonitor)
        self.__conmonitor_thread.start()

    def __conmonitor(self):
        while True:
            if self.__client:
                # The client should be connected: check that the socket
                # is still open (i.e. the server has not disconnected)
                with self.__client_lock:
                    if self.__client.is_closed():
                        self.__mark_invalid()

            if not self.__client:
                # The client is disconnected. Try to reconnect
                try:
                    self.__coninit(None)
                except Exception:
                    pass
                else:
                    logger.warning(
                        "connection to %s:%d[%s] established in "
                        "the background",
                        self.__host, self.__port, self.__target_name
                    )

            if self.__conmonitor_terminate:
                logger.debug("Terminate request received: closing client and "
                             "shutting down monitoring thread")
                if self.__client is not None:
                    with self.__client_lock:
                        self.__client.close_rpc()

                self.__conmonitor_thread = None
                break

            time.sleep(self.__retry)

    def __mark_invalid(self):
        logger.warning("connection to %s:%d[%s] failed. "
                       "It will be retried in the background",
                       self.__host, self.__port, self.__target_name)
        try:
            self.__client.close_rpc()
        except ConnectionError:
            pass
        finally:
            self.__client = None

    def close_rpc(self):
        """Closes the connection to the RPC server.

        No further method calls should be done after this method is called.
        """
        # Let the thread complete I/O and then do the socket closing.
        # Python fails to provide a way to cancel threads...
        self.__conmonitor_terminate = True

    def is_closed(self):
        if not self.__client:
            return True

        with self.__client_lock:
            return self.__client.is_closed()

    def __getattr__(self, name):
        """
        If the client is connected, pass this call onto the client. If not,
        return a method that returns None if the call was valid or if we can't
        tell. Raise AttributeError otherwise.
        """

        if (
            self.__valid_methods
            and name not in self.__valid_methods
            and name not in dir(Client)
        ):
            raise AttributeError
        else:
            # If the client exists, pass the call to the client
            def tryer(*args, **kwargs):
                if not self.__client:
                    return None

                with self.__client_lock:
                    client_method = getattr(self.__client, name)
                    try:
                        return client_method(*args, **kwargs)
                    except RPCConnectionError:
                        self.__mark_invalid()
                        return None
            return tryer


def _format_arguments(arguments):
    fmtargs = []
    for k, v in sorted(arguments.items(), key=itemgetter(0)):
        fmtargs.append(k + "=" + repr(v))
    if fmtargs:
        return ", ".join(fmtargs)
    else:
        return ""


class _PrettyPrintCall:
    def __init__(self, obj):
        self.obj = obj

    def __str__(self):
        r = self.obj["name"] + "("
        args = ", ".join([repr(a) for a in self.obj["args"]])
        r += args
        kwargs = _format_arguments(self.obj["kwargs"])
        if args and kwargs:
            r += ", "
        r += kwargs
        r += ")"
        return r


class Server(_AsyncioServer):
    """This class creates a TCP server that handles requests coming from
    *Client* objects (whether :class:`.Client`, :class:`.BestEffortClient`,
    or :class:`.AsyncioClient`).

    The server is designed using ``asyncio`` so that it can easily support
    multiple connections without the locking issues that arise in
    multi-threaded applications. Multiple connection support is useful even in
    simple cases: it allows new connections to be be accepted even when the
    previous client failed to properly shut down its connection.

    If a target method is a coroutine, it is awaited and its return value
    is sent to the RPC client. If ``allow_parallel`` is true, multiple
    target coroutines may be executed in parallel (one per RPC client),
    otherwise a lock ensures that the calls from several clients are executed
    sequentially.

    :param targets: A dictionary of objects providing the RPC methods to be
        exposed to the client. Keys are names identifying each object.
        Clients select one of these objects using its name upon connection.
    :param description: An optional human-readable string giving more
        information about the server.
    :param builtin_terminate: If set, the server provides a built-in
        ``terminate`` method that unblocks any tasks waiting on
        ``wait_terminate``. This is useful to handle server termination
        requests from clients.
    :param allow_parallel: Allow concurrent asyncio calls to the target's
        methods.
    """
    def __init__(self, targets, description=None, builtin_terminate=False,
                 allow_parallel=False):
        _AsyncioServer.__init__(self)
        self.targets = targets
        self.description = description
        self.builtin_terminate = builtin_terminate
        if builtin_terminate:
            self._terminate_request = asyncio.Event()
        if allow_parallel:
            self._noparallel = None
        else:
            self._noparallel = asyncio.Lock()

    @staticmethod
    def _document_function(function):
        """
        Turn a function into a tuple of its arguments and documentation.
        
        Allows remote inspection of what methods are available on a local device.
        
        Args:
            function (Callable): a Python function to be documented.
        
        Returns:
            Tuple[dict, str]: tuple of (argument specifications,
            function documentation).
            Any type annotations are converted to strings (for PYON serialization).
        """
        argspec_dict = dict(inspect.getfullargspec(function)._asdict())
        # Fix issue #1186: PYON can't serialize type annotations.
        if any(argspec_dict.get("annotations", {})):
            argspec_dict["annotations"] = str(argspec_dict["annotations"])
        return argspec_dict, inspect.getdoc(function)

    async def _process_action(self, target, obj):
        if self._noparallel is not None:
            await self._noparallel.acquire()
        try:
            if obj["action"] == "get_rpc_method_list":
                members = inspect.getmembers(target, inspect.ismethod)
                doc = {
                    "docstring": inspect.getdoc(target),
                    "methods": {}
                }
                for name, method in members:
                    if name.startswith("_"):
                        continue
                    method = getattr(target, name)
                    doc["methods"][name] = self._document_function(method)
                if self.builtin_terminate:
                    doc["methods"]["terminate"] = (
                        {
                            "args": ["self"],
                            "defaults": None,
                            "varargs": None,
                            "varkw": None,
                            "kwonlyargs": [],
                            "kwonlydefaults": [],
                        },
                        "Terminate the server.")
                logger.debug("RPC docs for %s: %s", target, doc)
                return doc
            elif obj["action"] == "call":
                logger.debug("calling %s", _PrettyPrintCall(obj))
                if (self.builtin_terminate and obj["name"] ==
                        "terminate"):
                    self._terminate_request.set()
                    return None
                else:
                    method = getattr(target, obj["name"])
                    ret = method(*obj["args"], **obj["kwargs"])
                    if inspect.iscoroutine(ret):
                        ret = await ret
                    return ret
            else:
                raise ValueError("Unknown action: {}"
                                 .format(obj["action"]))
        finally:
            if self._noparallel is not None:
                self._noparallel.release()

    async def _process_and_pyonize(self, target, obj):
        try:
            return pyon.encode({
                "status": "ok",
                "ret": await self._process_action(target, obj)
            })
        except (asyncio.CancelledError, SystemExit):
            raise
        except:
            return pyon.encode({
                "status": "failed",
                "exception": current_exc_packed()
            })

    async def _handle_connection_cr(self, reader, writer):
        try:
            line = await reader.readline()
            if line != _init_string:
                return

            obj = {
                "targets": sorted(self.targets.keys()),
                "description": self.description
            }
            line = pyon.encode(obj) + "\n"
            writer.write(line.encode())
            line = await reader.readline()
            if not line:
                return
            target_name = line.decode()[:-1]
            try:
                target = self.targets[target_name]
            except KeyError:
                return

            if callable(target):
                target = target()

            valid_methods = inspect.getmembers(target, inspect.ismethod)
            valid_methods = {m[0] for m in valid_methods}
            if self.builtin_terminate:
                valid_methods.add("terminate")
            writer.write((pyon.encode(valid_methods) + "\n").encode())

            while True:
                line = await reader.readline()
                if not line:
                    break
                reply = await self._process_and_pyonize(target,
                    pyon.decode(line.decode()))
                writer.write((reply + "\n").encode())
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            # May happens on Windows when client disconnects
            pass
        finally:
            writer.close()

    async def wait_terminate(self):
        await self._terminate_request.wait()


def simple_server_loop(targets, host, port, description=None):
    """Runs a server until an exception is raised (e.g. the user hits Ctrl-C)
    or termination is requested by a client.

    See :class:`sipyco.pc_rpc.Server` for a description of the parameters.
    """
    loop = asyncio.get_event_loop()
    try:
        server = Server(targets, description, True)
        loop.run_until_complete(server.start(host, port))
        try:
            loop.run_until_complete(server.wait_terminate())
        finally:
            loop.run_until_complete(server.stop())
    finally:
        loop.close()
