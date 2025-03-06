import asyncio
import time

async def TEST_ASYNC_FOR():
    BLK = 0.15  # appears as `time.sleep(BLK)` inside both for-loops
    NBLK = 0.16 # appears as `await asyncio.sleep(NBLK)` inside both for-loops
    GEN = 0.17  # appears as `time.sleep(GEN)` (`await asyncio.sleep(GEN)`) inside the standard (async) generator
    N = 3       # number of iterations in each for-loop
    
    def generator():
        for i in range(N):
            time.sleep(GEN) # slow I/O operation blocks thread
            yield i
    
    async def async_generator():
        for i in range(N):
            await asyncio.sleep(GEN) # slow I/O operation yields control to loop
            yield i
    
    async def standard_for():
        for i in generator():
            time.sleep(BLK) # CPU-intensive operation blocks thread
            await asyncio.sleep(NBLK) # slow I/O operation yields control to loop
    
    async def async_for():
        async for i in async_generator():
            time.sleep(BLK) # CPU-intensive operation blocks thread
            await asyncio.sleep(NBLK) # slow I/O operation yields control to loop
    
    t0 = time.perf_counter()
    await standard_for()
    print(f"1x for-loop:\t\t\t    {time.perf_counter()-t0:.2f} | expected: {N*BLK + N*NBLK + N*GEN:.2f} = N*BLK + N*NBLK + N*GEN")
    
    t0 = time.perf_counter()
    await async_for()
    print(f"1x async for-loop:\t\t    {time.perf_counter()-t0:.2f} | expected: {N*BLK + N*NBLK + N*GEN:.2f} = N*BLK + N*NBLK + N*GEN")
    
    def standard_for_duration(BLK, NBLK, GEN, N):
        t = 2*N*BLK + 2*N*GEN + NBLK + (N-1)*max(NBLK-(BLK+GEN), 0)
        return t, "2*N*BLK + 2*N*GEN + NBLK + (N-1)*max(NBLK-(BLK+GEN), 0)"
    
    t0 = time.perf_counter()
    await asyncio.gather(standard_for(), standard_for())
    t_st, expr_st = standard_for_duration(BLK, NBLK, GEN, N)
    print(f"2x for-loop (separate tasks):\t    {time.perf_counter()-t0:.2f} | expected: {t_st:.2f} = {expr_st}")
    
    def async_for_duration(BLK, NBLK, GEN, N):
        t = 2*N*BLK + N*GEN + NBLK + (N-1)*max(NBLK-BLK, 0) + (N-1)*GEN*(BLK > NBLK)*(NBLK > GEN) + GEN*(NBLK > BLK)*(BLK > GEN)
        return t, "2*N*BLK + N*GEN + NBLK + (N-1)*max(NBLK-BLK, 0) + (N-1)*GEN*(BLK > NBLK)*(NBLK > GEN) + GEN*(NBLK > BLK)*(BLK > GEN)"
    
    t0 = time.perf_counter()
    await asyncio.gather(async_for(), async_for())
    t_async, expr_async = async_for_duration(BLK, NBLK, GEN, N)
    print(f"2x async for-loop (separate tasks): {time.perf_counter()-t0:.2f} | expected: {t_async:.2f} = {expr_async}")

if __name__ == "__main__":
    asyncio.run(TEST_ASYNC_FOR())