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

from sipyco import keepalive, pyon, pyon_v1
from sipyco.tools import SignalHandler, AsyncioServer as _AsyncioServer
from sipyco.packed_exceptions import *

logger = logging.getLogger(__name__)


class AutoTarget:
    """Use this as target value in clients for them to automatically connect
    to the target exposed by the server. Servers must have only one target."""
    pass


class IncompatibleServer(Exception):
    """Raised by the client when attempting to connect to a server that does
    not have the expected target."""
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


def _socket_readline(socket, bufsize=4096):
    buf = socket.recv(bufsize).decode()
    offset = 0
    while buf.find("\n", offset) == -1:
        more = socket.recv(bufsize)
        if not more:
            raise EOFError("Connection closed before a full line was received.")
        buf += more.decode()
        offset += len(more)

    return buf


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

    The ``pyon_v2`` (PYON v2 encoding) feature is supported and selected
    when offered by the server. Future versions of the clients will require
    the ``pyon_v2`` feature.

    :param host: Identifier of the server. The string can represent a
        hostname or a IPv4 or IPv6 address (see
        ``socket.create_connection`` in the Python standard library).
    :param port: TCP port to use.
    :param target_name: Target name to select. ``IncompatibleServer`` is
        raised if the target does not exist.
        Use :class:`.AutoTarget` for automatic selection if the server has only one
        target.
        Use ``None`` to skip selecting a target. The list of targets can then
        be retrieved using :meth:`~sipyco.pc_rpc.Client.get_rpc_id`
        and then one can be selected later using :meth:`~sipyco.pc_rpc.Client.select_rpc_target`.
    :param ssl_config: Optional ``SimpleSSLConfig`` object for secure connections.
        If provided, SSL will be enabled with the specified certificates.
        See :class:`~sipyco.tools.SimpleSSLConfig` for more details.
    :param timeout: Socket operation timeout. Use ``None`` for blocking
        (default), ``0`` for non-blocking, and a finite value to raise
        ``socket.timeout`` if an operation does not complete within the
        given time. See also ``socket.create_connection()`` and
        ``socket.settimeout()`` in the Python standard library. A timeout
        in the middle of a RPC can break subsequent RPCs (from the same
        client).
    """

    def __init__(self, host, port, target_name=AutoTarget,
                 timeout=None, ssl_config=None):
        self.__socket = socket.create_connection((host, port), timeout)
        try:
            if ssl_config is not None:
                ssl_context = ssl_config.create_client_context()
                self.__socket = ssl_context.wrap_socket(self.__socket)
            self.__socket.sendall(_init_string)
            self.__features = ""
            self.__encode = pyon_v1.encode
            self.__decode = pyon_v1.decode
            server_identification = self.__recv()
            features = server_identification.get("features", [])
            if "pyon_v2" in features:
               self.__features += " pyon_v2"
               self.__encode = pyon.encode
               self.__decode = pyon.decode
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
        self.__socket.sendall((target_name + self.__features + "\n").encode())
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

    def close_rpc(self):
        """Closes the connection to the RPC server.

        No further method calls should be done after this method is called.
        """
        self.__socket.close()

    def __send(self, obj):
        line = self.__encode(obj) + "\n"
        self.__socket.sendall(line.encode())

    def __recv(self):
        line = _socket_readline(self.__socket)
        return self.__decode(line)

    def __do_action(self, action):
        self.__send(action)

        obj = self.__recv()
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
            raise AttributeError

        def proxy(*args, **kwargs):
            return self.__do_rpc(name, args, kwargs)
        return proxy


class AsyncioClient:
    """This class is similar to :class:`sipyco.pc_rpc.Client`, but
    uses ``asyncio`` instead of blocking calls.

    All RPC methods are coroutines.

    Concurrent access from different asyncio tasks is supported; all calls
    use a single lock.
    """

    def __init__(self):
        self.__lock = asyncio.Lock()
        self.__reader = None
        self.__writer = None
        self.__target_names = None
        self.__description = None
        self.__valid_methods = set()

    async def connect_rpc(self, host, port, target_name=AutoTarget, ssl_config=None):
        """Connects to the server. This cannot be done in __init__ because
        this method is a coroutine. See :class:`sipyco.pc_rpc.Client` for a description of the
        parameters."""
        ssl_context = None
        if ssl_config is not None:
            ssl_context = ssl_config.create_client_context()
        self.__reader, self.__writer = \
            await keepalive.async_open_connection(host, port, ssl=ssl_context, limit=100 * 1024 * 1024)
        try:
            self.__writer.write(_init_string)
            self.__features = ""
            self.__encode = pyon_v1.encode
            self.__decode = pyon_v1.decode
            server_identification = await self.__recv()
            features = server_identification.get("features", [])
            if "pyon_v2" in features:
                self.__features += " pyon_v2"
                self.__encode = pyon.encode
                self.__decode = pyon.decode
            self.__target_names = server_identification["targets"]
            self.__description = server_identification["description"]
            self.__selected_target = None
            self.__valid_methods = set()
            if target_name is not None:
                await self.select_rpc_target(target_name)
        except:
            await self.close_rpc()
            raise

    async def select_rpc_target(self, target_name):
        """Selects a RPC target by name. This function should be called
        exactly once if the connection was created with ``target_name=None``.
        """
        target_name = _validate_target_name(target_name, self.__target_names)
        self.__writer.write((target_name + self.__features + "\n").encode())
        self.__selected_target = target_name
        self.__valid_methods = await self.__recv()

    def get_selected_target(self):
        """Returns the selected target, or ``None`` if no target has been
        selected yet."""
        return self.__selected_target

    def get_local_host(self):
        """Returns the address of the local end of the connection."""
        return self.__writer.get_extra_info("socket").getsockname()[0]

    def get_rpc_id(self):
        """Returns a tuple (target_names, description) containing the
        identification information of the server."""
        return (self.__target_names, self.__description)

    async def close_rpc(self):
        """Closes the connection to the RPC server.

        No further method calls should be done after this method is called.
        """
        if self.__writer is not None:
            self.__writer.close()
            await self.__writer.wait_closed()
        self.__reader = None
        self.__writer = None
        self.__target_names = None
        self.__description = None

    def __send(self, obj):
        line = self.__encode(obj) + "\n"
        self.__writer.write(line.encode())

    async def __recv(self):
        line = await self.__reader.readline()
        if not line:
            raise EOFError("Connection closed unexpectedly")
        return self.__decode(line.decode())

    async def __do_rpc(self, name, args, kwargs):
        await self.__lock.acquire()
        try:
            obj = {"action": "call", "name": name,
                   "args": args, "kwargs": kwargs}
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

    def __getattr__(self, name):
        if name not in self.__valid_methods:
            raise AttributeError

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

    See :class:`sipyco.pc_rpc.Client` for a description of the other parameters.

    :param firstcon_timeout: Timeout to use during the first (blocking)
        connection attempt at object initialization.
    :param retry: Amount of time to wait between retries when reconnecting
        in the background.
    """

    def __init__(self, host, port, target_name, firstcon_timeout=1.0,
                 retry=5.0, ssl_config=None):
        self.__host = host
        self.__port = port
        self.__target_name = target_name
        self.__ssl_config = ssl_config
        self.__retry = retry

        self.__conretry_terminate = False
        self.__socket = None
        self.__valid_methods = set()
        try:
            self.__coninit(firstcon_timeout)
        except:
            logger.warning("first connection attempt to %s:%d[%s] failed, "
                           "retrying in the background",
                           self.__host, self.__port, self.__target_name,
                           exc_info=True)
            self.__start_conretry()
        else:
            self.__conretry_thread = None

    def __coninit(self, timeout):
        if timeout is None:
            self.__socket = socket.create_connection(
                (self.__host, self.__port))
        else:
            self.__socket = socket.create_connection(
                (self.__host, self.__port), timeout)
        if self.__ssl_config is not None:
            ssl_context = self.__ssl_config.create_client_context()
            self.__socket = ssl_context.wrap_socket(self.__socket)
        self.__socket.sendall(_init_string)
        self.__features = ""
        self.__encode = pyon_v1.encode
        self.__decode = pyon_v1.decode
        server_identification = self.__recv()
        features = server_identification.get("features", [])
        if "pyon_v2" in features:
            self.__features += " pyon_v2"
            self.__encode = pyon.encode
            self.__decode = pyon.decode
        target_name = _validate_target_name(self.__target_name,
                                            server_identification["targets"])
        self.__socket.sendall((target_name + self.__features + "\n").encode())
        self.__valid_methods = self.__recv()

        # Only after the initial handshake is complete, disable the socket
        # timeout (if any). Otherwise, the constructor can block forever if a
        # server accepts the connection but does not respond.
        self.__socket.settimeout(None)

    def __start_conretry(self):
        self.__conretry_thread = threading.Thread(target=self.__conretry)
        self.__conretry_thread.start()

    def __conretry(self):
        while True:
            try:
                self.__coninit(None)
            except:
                if self.__conretry_terminate:
                    break
                time.sleep(self.__retry)
            else:
                break
        if not self.__conretry_terminate:
            logger.warning("connection to %s:%d[%s] established in "
                           "the background",
                           self.__host, self.__port, self.__target_name)
        if self.__conretry_terminate and self.__socket is not None:
            self.__socket.close()
        # must be after __socket.close() to avoid race condition
        self.__conretry_thread = None

    def close_rpc(self):
        """Closes the connection to the RPC server.

        No further method calls should be done after this method is called.
        """
        if self.__conretry_thread is None:
            if self.__socket is not None:
                self.__socket.close()
        else:
            # Let the thread complete I/O and then do the socket closing.
            # Python fails to provide a way to cancel threads...
            self.__conretry_terminate = True

    def __send(self, obj):
        line = self.__encode(obj) + "\n"
        self.__socket.sendall(line.encode())

    def __recv(self):
        line = _socket_readline(self.__socket)
        return self.__decode(line)

    def __do_rpc(self, name, args, kwargs):
        if self.__conretry_thread is not None:
            return None

        obj = {"action": "call", "name": name, "args": args, "kwargs": kwargs}
        try:
            self.__send(obj)
            obj = self.__recv()
        except:
            logger.warning("connection failed while attempting "
                           "RPC to %s:%d[%s], re-establishing connection "
                           "in the background",
                           self.__host, self.__port, self.__target_name)
            self.__start_conretry()
            return None
        else:
            if obj["status"] == "ok":
                return obj["ret"]
            elif obj["status"] == "failed":
                raise_packed_exc(obj["exception"])
            else:
                raise ValueError

    def __getattr__(self, name):
        if name not in self.__valid_methods:
            raise AttributeError

        def proxy(*args, **kwargs):
            return self.__do_rpc(name, args, kwargs)
        return proxy

    def get_selected_target(self):
        raise NotImplementedError

    def get_local_host(self):
        raise NotImplementedError


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

    The ``pyon_v2`` (PYON v2 encoding) feature is supported and offered to
    the client. Future versions of ``Server`` will require the ``pyon_v2``
    feature.

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

    def __init__(self, targets, description="", builtin_terminate=False,
                 allow_parallel=False):
        _AsyncioServer.__init__(self)
        if any(" " in name for name in targets):
            raise ValueError("whitespace in target name")
        self.targets = targets
        if not isinstance(description, str):
            raise ValueError("description must be a `str`")
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
        if "annotations" in argspec_dict:
            argspec_dict["annotations"] = {k: v.__name__ for k, v in argspec_dict["annotations"].items()}
        return argspec_dict, inspect.getdoc(function)

    async def _process_action(self, target, obj):
        if self._noparallel is not None:
            await self._noparallel.acquire()
        try:
            if obj["action"] == "get_rpc_method_list":
                members = inspect.getmembers(target, callable)
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

    async def _process_and_pyonize(self, target, obj, encode):
        try:
            return encode({
                "status": "ok",
                "ret": await self._process_action(target, obj)
            })
        except asyncio.CancelledError:
            raise
        except SystemExit:
            if hasattr(self, "_terminate_request"):
                self._terminate_request.set()
            else:
                raise
        except:
            return encode({
                "status": "failed",
                "exception": current_exc_packed()
            })

    async def _handle_connection_cr(self, reader, writer):
        try:
            line = await reader.readline()
            if line != _init_string:
                return

            # For sipyco v2 and future servers this is encodable and decodable as
            # pure JSON (and PYON v2) or PYON v1.
            # For sipyco v1 servers it's PYON v1 if description == None.
            obj = {
                "targets": sorted(self.targets.keys()),
                "description": self.description,
                "features": ["pyon_v2"],
            }
            line = pyon.encode(obj) + "\n"
            writer.write(line.encode())
            line = await reader.readline()
            if not line:
                return
            target_name, *features = line.decode()[:-1].split(" ")

            encode = pyon_v1.encode
            decode = pyon_v1.decode
            for f in features:
                if f == "pyon_v2":
                    encode = pyon.encode
                    decode = pyon.decode
                else:
                    logger.warning("Unsupported feature `%s`", f)
                    return

            try:
                target = self.targets[target_name]
            except KeyError:
                return

            if callable(target):
                target = target()

            valid_methods = inspect.getmembers(target, callable)
            valid_methods = {m[0] for m in valid_methods}
            if self.builtin_terminate:
                valid_methods.add("terminate")
            writer.write((encode(valid_methods) + "\n").encode())

            while True:
                line = await reader.readline()
                if not line:
                    break
                reply = await self._process_and_pyonize(target,
                                                        decode(line.decode()),
                                                        encode)
                if reply is None:
                    return
                writer.write((reply + "\n").encode())
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            # May happens on Windows when client disconnects
            pass
        finally:
            writer.close()

    async def wait_terminate(self):
        await self._terminate_request.wait()


def simple_server_loop(targets, host, port, description=None, allow_parallel=False,
                       ssl_config=None, *, loop=None):
    """Runs a server until an exception is raised (e.g. the user hits Ctrl-C)
    or termination is requested by a client.

    See :class:`sipyco.pc_rpc.Server` for a description of the parameters.
    """
    if loop is None:
        used_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(used_loop)
    else:
        used_loop = loop
    try:
        signal_handler = SignalHandler()
        signal_handler.setup()
        try:
            server = Server(targets, description, True, allow_parallel)
            used_loop.run_until_complete(server.start(host, port, ssl_config))
            try:
                _, pending = used_loop.run_until_complete(asyncio.wait(
                    [used_loop.create_task(signal_handler.wait_terminate()),
                     used_loop.create_task(server.wait_terminate())],
                    return_when=asyncio.FIRST_COMPLETED))
                for task in pending:
                    task.cancel()
            finally:
                used_loop.run_until_complete(server.stop())
        finally:
            signal_handler.teardown()
    finally:
        if loop is None:
            used_loop.close()
