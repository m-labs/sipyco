import asyncio
import atexit

async def f(loop):
    print(loop.is_running())

def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    atexit.register(loop.close)
    
    print(loop.is_running())
    loop.run_until_complete(f(loop))
    print(loop.is_running())

if __name__ == "__main__":
    main()