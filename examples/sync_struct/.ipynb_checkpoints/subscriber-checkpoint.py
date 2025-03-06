import asyncio
import atexit
import signal
import time

from sipyco.asyncio_tools import atexit_register_coroutine
from sipyco.sync_struct import Subscriber

async def run_forever(shutdown_event):
    try:
        await shutdown_event.wait()
    except asyncio.CancelledError:
        pass
    print("\nStopping run_forever().")

def verbose_before_connect(notifier_name):
    def f():
        print(f"{time.time():.2f}: {notifier_name}.before_receive_cb() called")
    return f

def verbose_builder(notifier_name):
    def f(obj):
        print(f"{time.time():.2f}: {notifier_name}.target_builder(obj) called with obj =", obj)
        return obj
    return f

def verbose_notify(notifier_name):
    def f(mod):
        print(f"{time.time():.2f}: {notifier_name}.notify_cb(mod) called with mod =", mod)
    return f

def verbose_disconnect(notifier_name, shutdown_event):
    def f():
        print(f"{time.time():.2f}: {notifier_name}.disconnect_cb() called")
        shutdown_event.set()
    return f

def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    atexit.register(loop.close)

    shutdown_event = asyncio.Event()

    subscribers = {}
    for notifier_name in [f"notifier{i}" for i in range(3)]:
        subscribers[notifier_name] = Subscriber(
            notifier_name = notifier_name,
            target_builder = verbose_builder(notifier_name),
            notify_cb = verbose_notify(notifier_name),
            disconnect_cb = verbose_disconnect(notifier_name, shutdown_event),
        )
        loop.run_until_complete(subscribers[notifier_name].connect("localhost", 5000, before_receive_cb=verbose_before_connect(notifier_name)))
        atexit_register_coroutine(subscribers[notifier_name].close, loop=loop)

    task = loop.create_task(run_forever(shutdown_event))
    loop.add_signal_handler(signal.SIGINT, task.cancel)
    loop.run_until_complete(task)

if __name__ == "__main__":
    main()