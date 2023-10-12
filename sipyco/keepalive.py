import asyncio
import logging
import socket
import sys
from typing import Any, Optional

logger = logging.getLogger(__name__)


def set_keepalive(
        sock: socket,
        after_idle: Optional[int] = None,
        interval: Optional[int] = None,
        max_fails: Optional[int] = None,
):
    """ Turn on keepalive and set options for socket

    Args:
        sock: The socket to target
        after_idle: How long (in seconds) that the socket will be idle for
            before sending the first keep alive.
        interval: Time (in seconds) between keep alive packets.
        max_fails: Number of probes to send before the connection fails.
            Ignored on Windows, normally 5 or 10.

    The defaults for the arguments are taken from the OS level defaults. These
    can be controlled using sysctl on Linux, or the registry on Windows.
    Normally it is sufficient to set these correctly only at one end of the
    connection, the server is most convenient for this.

    On Windows both or neither of after_idle and interval must be supplied and
    max_fails is ignored. On all other OSs other than Linux all the arguments
    are ignored.
    """
    # This is pretty portable actually, it works on at least Linux, Windows,
    # some BSDs and Solaris.
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

    if sys.platform.startswith("linux"):
        if after_idle is not None:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, after_idle)
        if interval is not None:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, interval)
        if max_fails is not None:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, max_fails)
    elif sys.platform.startswith("win") or sys.platform.startswith("cygwin"):
        # setting max_fails is not supported, typically ends up being 5 or 10
        # depending on Windows version
        if after_idle is not None and interval is not None:
            sock.ioctl(socket.SIO_KEEPALIVE_VALS,
                       (1, after_idle * 1000, interval * 1000))
        elif after_idle is not None or interval is not None:
            raise ValueError(
                "Both or neither of after_idle and interval must be set on windows"
            )

    elif after_idle is not None or interval is not None or max_fails is not None:
        logger.warning(
            "Setting TCP keepalive options is not supported on %s",
            sys.platform
        )


async def async_open_connection(
        host: str,
        port: int,
        *args: Any,
        after_idle: Optional[int] = None,
        interval: Optional[int] = None,
        max_fails: Optional[int] = None,
        **kwargs: Any,
):
    """ Open a socket and set keepalive options

    Calls asyncio.open_connection to create the connection and set_keepalive to
    setup the keepalive. Accepts all the arguments that asyncio.open_connection
    does plus the after_idle, interval and max_fails arguments which are
    forwarded to set_keepalive.
    """
    reader, writer = await asyncio.open_connection(host, port, *args, **kwargs)
    transport_socket = writer.get_extra_info('socket')
    # Using native socket to call deprecated `ioctl` in `TransportSocket`  
    # wrapper in Python 3.11. See https://github.com/python/cpython/pull/24538
    sock = transport_socket._sock
    set_keepalive(sock, after_idle, interval, max_fails)
    return reader, writer


def create_connection(
        host: str,
        port: int,
        *args: Any,
        after_idle: Optional[int] = None,
        interval: Optional[int] = None,
        max_fails: Optional[int] = None,
        **kwargs: Any,
):
    """Open a socket and set keepalive options

    Calls socket.create_connection to create the connection and set_keepalive to
    setup the keepalive. Accepts all the arguments that socket.create_connection
    except that host and port are passed separately and used to form the address
    tuple expected by socket.create_connection. Plus the after_idle, interval
    and max_fails arguments which are forwarded to set_keepalive.
    """
    sock = socket.create_connection((host, port), *args, **kwargs)
    set_keepalive(sock, after_idle, interval, max_fails)
    return sock
