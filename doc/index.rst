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

:mod:`sipyco.asyncio_tools` module
----------------------------------

.. automodule:: sipyco.asyncio_tools
    :members:

:mod:`sipyco.logging_tools` module
----------------------------------

.. automodule:: sipyco.logging_tools
    :members:



Remote Procedure Call tool
==========================

This tool is the preferred way of handling simple RPC servers.
Instead of writing a client for simple cases, you can simply use this tool
to call remote functions of an RPC server.

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
