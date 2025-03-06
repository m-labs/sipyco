import asyncio
import atexit
import signal

from sipyco.asyncio_tools import atexit_register_coroutine
from sipyco.broadcast import Broadcaster

async def endless_broadcasts(broadcaster):
    print("Starting loop of endless broadcasts.")
    i = 0
    try:
        while True:
            await asyncio.sleep(1)
            for receiver_name in [f"receiver{i}" for i in range(3)]:
                message = f"{receiver_name}: broadcast {i}"
                broadcaster.broadcast(receiver_name, message)
            print(f"{{receiver_name}}: broadcast {i}")
            i += 1
    except asyncio.CancelledError:
        print("\nStopping loop of endless broadcasts.")

def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    atexit.register(loop.close)
    
    broadcaster = Broadcaster()
    loop.run_until_complete(broadcaster.start("localhost", 5000))
    atexit_register_coroutine(broadcaster.stop, loop=loop)

    task = loop.create_task(endless_broadcasts(broadcaster))
    loop.add_signal_handler(signal.SIGINT, task.cancel)
    loop.run_until_complete(task)

if __name__ == "__main__":
    main()