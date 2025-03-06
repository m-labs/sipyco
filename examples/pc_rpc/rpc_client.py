import time
import string
import random

from sipyco.pc_rpc import Client as RPCClient

def main():
    rpc_clients = {name : RPCClient("localhost", 5000, name) for name in [f"LocalObject{i}" for i in range(3)]}
    remote_method_names = [f"method{i}" for i in range(3)]
    try:
        while True:
            for name, client in rpc_clients.items():
                for method_name in remote_method_names:
                    time.sleep(1)
                    random_message = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
                    print(f"Remote '{name}' at timestamp {client.get_time():.3f}: Calling {name}.{method_name}(msg) with random msg = {random_message}")
                    getattr(client, method_name)(random_message)
    except KeyboardInterrupt:
        print("\nBye!")

if __name__ == "__main__":
    main()