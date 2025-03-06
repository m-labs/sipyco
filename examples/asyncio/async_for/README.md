# Example scripts with "async for"

### How-To: Run

Open a terminal session and run `python async_for.py`.

### What is the goal?

To understand `async for` and, by logical extension, `async with`. In summary:

- One can always turn a generator (context manager), that starts with `def`, into an awaitable generator (awaitable context manager), that starts with `async def`.
- Then, one is forced to replace `for [...] in [generator]` (`with [context manager] as [...]`) by `async for [...] in [awaitable generator]` (`async with [awaitable context manager] as [...]`) wherever that generator (context manager) is used.
- This lowers the overall execution time of a program if the `[generator]` (context manager) contains some slow I/O operation that can be turned into a coroutine and awaited while other code runs.
- For clarity: A single `for`-loop (`with`-context) by itself is not sped up at all by `async for` (`async with`) because the code inside the `async for`-loop (`async with`-context) can only run __after__ the awaitable generator (awaitable context manager) has been evaluated.
- This seems to be the only use of `async for` (`async with`).

### Related posts

- [https://stackoverflow.com/questions/67092070/why-do-we-need-async-for-and-async-with](https://stackoverflow.com/questions/67092070/why-do-we-need-async-for-and-async-with)
- [https://stackoverflow.com/questions/79481850/when-is-async-for-faster-than-for-python](https://stackoverflow.com/questions/79481850/when-is-async-for-faster-than-for-python)