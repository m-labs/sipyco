import asyncio
import atexit
import signal

from sipyco.asyncio_tools import atexit_register_coroutine
from sipyco.sync_struct import Notifier, Publisher

async def endless_modifications(notifiers):
    print("Starting loop of endless modifications.")
    i = 0
    try:
        while True:
            await asyncio.sleep(1)
            for name, notifier in notifiers.items():
                notifier[f"var{i}"] = f"{name}_{i}"
            print(f'set "var{i}" = "{{name}}_{i}"')
            i += 1
    except asyncio.CancelledError:
        print("\nStopping loop of endless modifications.")

def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    atexit.register(loop.close)

    notifiers = {name : Notifier(dict()) for name in [f"notifier{i}" for i in range(3)]}
    publisher = Publisher(notifiers)
    loop.run_until_complete(publisher.start("localhost", 5000))
    atexit_register_coroutine(publisher.stop, loop=loop)

    task = loop.create_task(endless_modifications(notifiers))
    loop.add_signal_handler(signal.SIGINT, task.cancel)
    loop.run_until_complete(task)

if __name__ == "__main__":
    main()