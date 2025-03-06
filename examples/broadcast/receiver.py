import asyncio
import atexit
import signal
import time

from sipyco.asyncio_tools import atexit_register_coroutine
from sipyco.broadcast import Receiver

async def run_forever(shutdown_event):
    try:
        await shutdown_event.wait()
    except asyncio.CancelledError:
        pass
    print("\nStopping run_forever().")

def verbose_notify(name):
    def f(obj):
        print(f"{time.time():.2f}: {name}.notify_cb(obj) called with obj =", obj)
    return f

def verbose_disconnect(name, shutdown_event):
    def f():
        print(f"{time.time():.2f}: {name}.disconnect_cb() called")
        shutdown_event.set()
    return f

def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    atexit.register(loop.close)

    shutdown_event = asyncio.Event()

    receivers = {}
    for name in [f"receiver{i}" for i in range(3)]:
        receivers[name] = Receiver(
            name = name,
            notify_cb = verbose_notify(name),
            disconnect_cb = verbose_disconnect(name, shutdown_event),
        )
        loop.run_until_complete(receivers[name].connect("localhost", 5000))
        atexit_register_coroutine(receivers[name].close, loop=loop)

    task = loop.create_task(run_forever(shutdown_event))
    loop.add_signal_handler(signal.SIGINT, task.cancel)
    loop.run_until_complete(task)

if __name__ == "__main__":
    main()