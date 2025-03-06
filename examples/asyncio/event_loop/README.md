# Example scripts for the asyncio event loop

### How-To: Run

Open a terminal session and run `python event_loop.py`.

### Comments

- Calling `loop.run_until_complete(asyncio.start_server([...]))` ([asyncio.start_server](https://docs.python.org/3/library/asyncio-stream.html#asyncio.start_server) and [loop.run_until_complete](https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.run_until_complete)) returns immediately after the server is set up, so the server does __not__ run yet.
- The server runs exactly as long as the event loop runs. Temporarily (permanently) running the event loop temporarily (permanently) runs the server.
- This all works because the server registers callbacks with the event loop and lets the event loop handle triggering on incoming connections.