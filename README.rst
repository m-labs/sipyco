SiPyCo
======

SiPyCo (**Si**mple **Py**thon **Co**mmunications) is a library for writing networked Python programs.  
It was originally part of ARTIQ, and was split out to enable light-weight programs to be written without a dependency on ARTIQ.

Documentation
-------------

Documentation is available `here <https://m-labs.hk/artiq/sipyco-manual/>`_.

Installation
------------

Using pip
~~~~~~~~~

.. code-block:: bash

   pip install git+https://github.com/m-labs/sipyco


Inside a Python project
~~~~~~~~~~~~~~~~~~~~~~~

Add to ``pyproject.toml``

.. code-block:: toml

   dependencies = [
     "sipyco @ git+https://github.com/m-labs/sipyco",
   ]
