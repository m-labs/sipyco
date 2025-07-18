"""This module helps synchronizing a mutable Python structure owned and
modified by one process (the *publisher*) with copies of it (the
*subscribers*) in different processes and possibly different machines.

Synchronization is achieved by sending a full copy of the structure to each
subscriber upon connection (*initialization*), followed by dictionaries
describing each modification made to the structure (*mods*, see
:class:`ModAction`).

Structures must be PYON serializable and contain only lists, dicts, and
immutable types. Lists and dicts can be nested arbitrarily.
"""

import asyncio
from enum import Enum, unique
from operator import getitem
from functools import partial
import logging

from sipyco import keepalive, pyon
from sipyco.tools import AsyncioServer


logger = logging.getLogger(__name__)


_protocol_banner = b"ARTIQ sync_struct\n"


@unique
class ModAction(Enum):
    """Describes the type of incremental modification.

    `Mods` are represented by a dictionary ``m``. ``m["action"]`` describes
    the type of modification, as per this enum, serialized as a string if
    required.

    The path (member field) the change applies to is given in
    ``m["path"]`` as a list; elements give successive levels of indexing.
    (There is no ``path`` on initial initialization.)

    Details on the modification are stored in additional data fields specific
    to each type.

    For example, this represents appending the value ``42`` to an array
    ``data.counts[0]``: ::

        {
            "action": "append",
            "path": ["data", "counts", 0],
            "x": 42
        }
    """

    #: A full copy of the data is sent in `struct`; no `path` given.
    init = "init"

    #: Appends `x` to target list.
    append = "append"

    #: Inserts `x` into target list at index `i`.
    insert = "insert"

    #: Removes index `i` from target list.
    pop = "pop"

    #: Sets target's `key` to `value`.
    setitem = "setitem"

    #: Removes target's `key`.
    delitem = "delitem"


# Handlers to apply a given mod to a target dict, invoked with (target, mod).
_mod_appliers = {
    ModAction.append: lambda t, m: t.append(m["x"]),
    ModAction.insert: lambda t, m: t.insert(m["i"], m["x"]),
    ModAction.pop: lambda t, m: t.pop(m["i"]),
    ModAction.setitem: lambda t, m: t.__setitem__(m["key"], m["value"]),
    ModAction.delitem: lambda t, m: t.__delitem__(m["key"])
}


def process_mod(target, mod):
    """Apply a *mod* to the target, mutating it."""
    for key in mod["path"]:
        target = getitem(target, key)

    _mod_appliers[ModAction(mod["action"])](target, mod)


class Subscriber:
    """An asyncio-based client to connect to a ``Publisher``.

    :param notifier_name: Name of the notifier to subscribe to.
    :param target_builder: A function called during initialization that takes
        the object received from the publisher and returns the corresponding
        local structure to use. Can be identity.
    :param notify_cb: An optional function called every time a mod is received
        from the publisher. The mod is passed as parameter. The function is
        called after the mod has been processed.
        A list of functions may also be used, and they will be called in turn.
    :param disconnect_cb: An optional function called when disconnection
        happens from external causes (i.e. not when ``close`` is called).
    :param ssl_config: Optional ``SimpleSSLConfig`` object for secure connections.
        If provided, SSL will be enabled with the specified certificates.
        See :class:`~sipyco.tools.SimpleSSLConfig` for more details.
    """
    def __init__(self, notifier_name, target_builder, notify_cb=None,
                 disconnect_cb=None):
        self.notifier_name = notifier_name
        self.target_builder = target_builder
        if notify_cb is None:
            notify_cb = []
        if not isinstance(notify_cb, list):
            notify_cb = [notify_cb]
        self.notify_cbs = notify_cb
        self.disconnect_cb = disconnect_cb

    async def connect(self, host, port, before_receive_cb=None, ssl_config=None):
        ssl_context = None
        if ssl_config is not None:
            ssl_context = ssl_config.create_client_context()
        self.reader, self.writer = \
            await keepalive.async_open_connection(host, port, limit=100 * 1024 * 1024,
                                                  ssl=ssl_context)
        try:
            if before_receive_cb is not None:
                before_receive_cb()
            self.writer.write(_protocol_banner)
            self.writer.write((self.notifier_name + "\n").encode())
            self.receive_task = asyncio.ensure_future(self._receive_cr())
        except:
            self.writer.close()
            del self.reader
            del self.writer
            raise

    async def close(self):
        self.disconnect_cb = None
        try:
            self.receive_task.cancel()
            try:
                await asyncio.wait_for(self.receive_task, None)
            except asyncio.CancelledError:
                pass
        finally:
            self.writer.close()
            del self.reader
            del self.writer

    async def _receive_cr(self):
        try:
            target = None
            while True:
                line = await self.reader.readline()
                if not line:
                    return
                mod = pyon.decode(line.decode())

                if mod["action"] == "init":
                    target = self.target_builder(mod["struct"])
                else:
                    process_mod(target, mod)

                try:
                    for notify_cb in self.notify_cbs:
                        notify_cb(mod)
                except:
                    logger.error("Exception in notifier callback",
                                 exc_info=True)
                    break

        except ConnectionError:
            pass
        finally:
            if self.disconnect_cb is not None:
                self.disconnect_cb()


class Notifier:
    """Encapsulates a structure whose changes need to be published.

    All mutations to the structure must be made through the :class:`.Notifier`.
    The original structure must only be accessed for reads.

    In addition to the list methods below, the :class:`.Notifier` supports the
    index syntax for modification and deletion of elements. Modification of
    nested structures can be also done using the index syntax, for example:

    >>> n = Notifier([])
    >>> n.append([])
    >>> n[0].append(42)
    >>> n.raw_view
    [[42]]

    This class does not perform any network I/O and is meant to be used with
    e.g. the :class:`.Publisher` for this purpose. Only one publisher at most
    can be associated with a :class:`.Notifier`.

    :param backing_struct: Structure to encapsulate.
    """
    def __init__(self, backing_struct, root=None, path=[]):
        #: The raw data encapsulated (read-only!).
        self.raw_view = backing_struct

        if root is None:
            self.root = self
            self.publish = None
        else:
            self.root = root
        self._backing_struct = backing_struct
        self._path = path

    # Backing struct modification methods.
    # All modifications must go through them!

    def append(self, x):
        """Append to a list."""
        self._backing_struct.append(x)
        if self.root.publish is not None:
            self.root.publish({"action": ModAction.append.value,
                               "path": self._path,
                               "x": x})

    def insert(self, i, x):
        """Insert an element into a list."""
        self._backing_struct.insert(i, x)
        if self.root.publish is not None:
            self.root.publish({"action": ModAction.insert.value,
                               "path": self._path,
                               "i": i, "x": x})

    def pop(self, i=-1):
        """Pop an element from a list. The returned element is not
        encapsulated in a :class:`.Notifier` and its mutations are no longer
        tracked."""
        r = self._backing_struct.pop(i)
        if self.root.publish is not None:
            self.root.publish({"action": ModAction.pop.value,
                               "path": self._path,
                               "i": i})
        return r

    def __setitem__(self, key, value):
        self._backing_struct.__setitem__(key, value)
        if self.root.publish is not None:
            self.root.publish({"action": ModAction.setitem.value,
                               "path": self._path,
                               "key": key,
                               "value": value})

    def __delitem__(self, key):
        self._backing_struct.__delitem__(key)
        if self.root.publish is not None:
            self.root.publish({"action": ModAction.delitem.value,
                               "path": self._path,
                               "key": key})

    def __getitem__(self, key):
        item = getitem(self._backing_struct, key)
        return Notifier(item, self.root, self._path + [key])


def update_from_dict(target, source):
    """Updates notifier contents from given source dictionary.

    Only the necessary changes are performed; unchanged fields are not written.
    (Currently, modifications are only performed at the top level. That is,
    whenever there is a change to a child array/struct the entire member is
    updated instead of choosing a more optimal set of mods.)
    """
    curr = target.raw_view

    # Delete removed keys.
    for k in list(curr.keys()):
        if k not in source:
            del target[k]

    # Insert/update changed data.
    for k in source.keys():
        if k not in curr or curr[k] != source[k]:
            target[k] = source[k]


class Publisher(AsyncioServer):
    """A network server that publish changes to structures encapsulated in
    a :class:`.Notifier`.

    :param notifiers: A dictionary containing the notifiers to associate with
        the :class:`.Publisher`. The keys of the dictionary are the names of
        the notifiers to be used with :class:`.Subscriber`.
    """
    def __init__(self, notifiers):
        AsyncioServer.__init__(self)
        self.notifiers = notifiers
        self._recipients = {k: set() for k in notifiers.keys()}
        self._notifier_names = {id(v): k for k, v in notifiers.items()}

        for notifier in notifiers.values():
            notifier.publish = partial(self.publish, notifier)

    async def _handle_connection_cr(self, reader, writer):
        try:
            line = await reader.readline()
            if line != _protocol_banner:
                return

            line = await reader.readline()
            if not line:
                return
            notifier_name = line.decode()[:-1]

            try:
                notifier = self.notifiers[notifier_name]
            except KeyError:
                return

            obj = {"action": ModAction.init.value, "struct": notifier.raw_view}
            line = pyon.encode(obj) + "\n"
            writer.write(line.encode())

            queue = asyncio.Queue()
            self._recipients[notifier_name].add(queue)
            try:
                while True:
                    line = await queue.get()
                    writer.write(line)
                    # raise exception on connection error
                    await writer.drain()
            finally:
                self._recipients[notifier_name].remove(queue)
        except (ConnectionError, TimeoutError):
            # subscribers disconnecting are a normal occurrence
            pass

    def publish(self, notifier, mod):
        line = pyon.encode(mod) + "\n"
        line = line.encode()
        notifier_name = self._notifier_names[id(notifier)]
        for recipient in self._recipients[notifier_name]:
            recipient.put_nowait(line)
