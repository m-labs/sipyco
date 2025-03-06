import asyncio
import atexit
import signal
import time

from sipyco.asyncio_tools import atexit_register_coroutine
from sipyco.pc_rpc import Server as RPCServer

async def run_forever(shutdown_event):
    try:
        await shutdown_event.wait()
    except asyncio.CancelledError:
        pass
    print("\nStopping run_forever().")

class LocalObject:
    def __init__(self, name):
        self.name = name
        self.__t0 = time.time()
    def get_time(self):
        return time.time() - self.__t0

def method_factory(method_name):
    def f(self, msg):
        print(f"'{self.name}' at timestamp {self.get_time():.3f}: Received call to: {self.name}.{method_name}(msg) with msg = {msg}")
    return f

for method_name in [f"method{i}" for i in range(3)]:
    setattr(LocalObject, method_name, method_factory(method_name))

def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    atexit.register(loop.close)

    local_objects = {name : LocalObject(name) for name in [f"LocalObject{i}" for i in range(3)]}
    
    rpc_server = RPCServer(local_objects, allow_parallel=True)
    loop.run_until_complete(rpc_server.start("localhost", 5000))
    atexit_register_coroutine(rpc_server.stop, loop=loop)

    task = loop.create_task(run_forever(asyncio.Event()))
    loop.add_signal_handler(signal.SIGINT, task.cancel)
    loop.run_until_complete(task)

if __name__ == "__main__":
    main()