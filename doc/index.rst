Introduction
============

SiPyCo (Simple Python Communications) is a library for writing networked Python programs. It was originally part of ARTIQ, and was split out to enable light-weight programs to be written without a dependency on ARTIQ.

API documentation
=================

:mod:`sipyco.pyon` module
-------------------------

.. automodule:: sipyco.pyon
    :members:


:mod:`sipyco.pc_rpc` module
---------------------------

.. automodule:: sipyco.pc_rpc
    :members:


:mod:`sipyco.fire_and_forget` module
------------------------------------

.. automodule:: sipyco.fire_and_forget
    :members:


:mod:`sipyco.sync_struct` module
--------------------------------

.. automodule:: sipyco.sync_struct
    :members:


:mod:`sipyco.remote_exec` module
--------------------------------

.. automodule:: sipyco.remote_exec
    :members:

:mod:`sipyco.common_args` module
--------------------------------

.. automodule:: sipyco.common_args
    :members:

:mod:`sipyco.tools` module
----------------------------------

.. automodule:: sipyco.tools
    :members:

:mod:`sipyco.logging_tools` module
----------------------------------

.. automodule:: sipyco.logging_tools
    :members:



Remote Procedure Call tool
==========================

This tool is the preferred way of handling simple RPC servers.
Instead of writing a client for simple cases, you can simply use this tool
to call remote functions of an RPC server. For secure connections, see `SSL Setup`_.

* Listing existing targets

        The ``list-targets`` sub-command will print to standard output the
        target list of the remote server::

            $ sipyco_rpctool hostname port list-targets

* Listing callable functions

        The ``list-methods`` sub-command will print to standard output a sorted
        list of the functions you can call on the remote server's target.

        The list will contain function names, signatures (arguments) and
        docstrings.

        If the server has only one target, you can do::

            $ sipyco_rpctool hostname port list-methods

        Otherwise you need to specify the target, using the ``-t target``
        option::

            $ sipyco_rpctool hostname port list-methods -t target_name

* Remotely calling a function

        The ``call`` sub-command will call a function on the specified remote
        server's target, passing the specified arguments.
        Like with the previous sub-command, you only need to provide the target
        name (with ``-t target``) if the server hosts several targets.

        The following example will call the ``set_attenuation`` method of the
        Lda controller with the argument ``5``::

            $ sipyco_rpctool ::1 3253 call -t lda set_attenuation 5

        In general, to call a function named ``f`` with N arguments named
        respectively ``x1, x2, ..., xN`` you can do::

            $ sipyco_rpctool hostname port call -t target f x1 x2 ... xN

        You can use Python syntax to compute arguments as they will be passed
        to the ``eval()`` primitive. The numpy package is available in the namespace
        as ``np``. Beware to use quotes to separate arguments which use spaces::

            $ sipyco_rpctool hostname port call -t target f '3 * 4 + 2' True '[1, 2]'
            $ sipyco_rpctool ::1 3256 call load_sample_values 'np.array([1.0, 2.0], dtype=float)'

        If the called function has a return value, it will get printed to
        the standard output if the value is not None like in the standard
        python interactive console::

            $ sipyco_rpctool ::1 3253 call get_attenuation
            5.0

Command-line details:

.. argparse::
   :ref: sipyco.sipyco_rpctool.get_argparser
   :prog: sipyco_rpctool


SSL Setup
=========

SiPyCo supports SSL/TLS encryption with mutual authentication for secure communication, but it is disabled by default. To enable and use SSL, follow these steps:

**Generate key and certificate:**

Run the following command twice, once with server filenames (e.g., ``server.key``, ``server.pem``) and once with client filenames (e.g., ``client.key``, ``client.pem``):

.. code-block:: bash

   openssl req -x509 -newkey rsa -keyout <filename>.key -nodes -out <filename>.pem -sha256 -subj "/"

.. note::
    The ``-subj "/"`` parameter bypasses the interactive prompts for certificate information (country, organization, etc.) that OpenSSL normally requires.

A single client certificate must be shared among multiple clients. This reduces certificate management overhead, as the server only needs to trust one client certificate. SiPyCo's SSL implementation is configured to authenticate based on certificates directly, rather than hostname verification, making this approach secure for trusted environments where certificate distribution is controlled.

Enabling SSL
------------

To start with SSL enabled, the server requires its own key and certificate, as well as the certificate of a client to trust. Similarly, the client requires its own key and certificate, as well as the certificate of a server to trust.

**For servers:**

.. code-block:: python

    from sipyco.pc_rpc import simple_server_loop
    from sipyco.tools import SimpleSSLConfig


    ssl_config = SimpleSSLConfig(local_cert="path/to/server.pem",
                                 local_key="path/to/server.key",
                                 peer_cert="path/to/client.pem")

    simple_server_loop(targets, host, port, ssl_config=ssl_config)

**For clients:**

.. code-block:: python

    from sipyco.tools import SimpleSSLConfig


    ssl_config = SimpleSSLConfig(local_cert="path/to/client.pem",
                                 local_key="path/to/client.key",
                                 peer_cert="path/to/server.pem")

    client = Client(host, port, ssl_config=ssl_config)
