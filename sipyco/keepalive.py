import asyncio
import logging
import socket
import sys

logger = logging.getLogger(__name__)


def set_keepalive(sock: socket, after_idle=10, interval=10, max_fails=3):
    if sys.platform.startswith("linux"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, after_idle)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, interval)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, max_fails)
    elif sys.platform.startswith("win") or sys.platform.startswith("cygwin"):
        # setting max_fails is not supported, typically ends up being 5 or 10
        # depending on Windows version
        sock.ioctl(socket.SIO_KEEPALIVE_VALS,
                   (1, after_idle * 1000, interval * 1000))
    else:
        logger.warning("TCP keepalive not supported on platform '%s', ignored",
                       sys.platform)


async def open_connection(host,
                          port,
                          after_idle=10,
                          interval=10,
                          max_fails=3,
                          *args,
                          **kwargs):
    reader, writer = await asyncio.open_connection(host, port, *args, **kwargs)
    sock = writer.get_extra_info('socket')
    set_keepalive(sock, after_idle, interval, max_fails)
    return reader, writer
