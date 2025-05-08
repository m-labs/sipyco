import logging

from sipyco.logging_tools import multiline_log_config


def verbosity_args(parser):
    """
    Adds `-v`/`-q` arguments that increase or decrease the default logging levels. 
    Repeat for higher levels.
    """
    group = parser.add_argument_group("verbosity")
    group.add_argument("-v", "--verbose", default=0, action="count",
                       help="increase logging level")
    group.add_argument("-q", "--quiet", default=0, action="count",
                       help="decrease logging level")


def init_logger_from_args(args):
    multiline_log_config(
        level=logging.WARNING + args.quiet*10 - args.verbose*10)


def simple_network_args(parser, default_port, ssl=False):
    group = parser.add_argument_group("network server")
    group.add_argument(
        "--bind", default=[], action="append",
        help="additional hostname or IP address to bind to; "
        "use '*' to bind to all interfaces (default: %(default)s)")
    group.add_argument(
        "--no-localhost-bind", default=False, action="store_true",
        help="do not implicitly also bind to localhost addresses")
    if isinstance(default_port, int):
        group.add_argument("-p", "--port", default=default_port, type=int,
                           help="TCP port to listen on (default: %(default)d)")
    else:
        for name, purpose, default in default_port:
            h = ("TCP port for {} connections (default: {})"
                 .format(purpose, default))
            group.add_argument("--port-" + name, default=default, type=int,
                               help=h)
    if ssl:
        group.add_argument(
            "--ssl", nargs=3, metavar=('CERT', 'KEY', 'PEER'), default=None,
            help="Enable SSL authentication: "
                "CERT: server certificate file, "
                "KEY: server private key, "
                "PEER: client certificate to trust "
                "(default: %(default)s)")


def bind_address_from_args(args):
    if "*" in args.bind:
        return None
    if args.no_localhost_bind:
        return args.bind
    else:
        return ["127.0.0.1", "::1"] + args.bind
