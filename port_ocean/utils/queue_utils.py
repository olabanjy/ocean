import asyncio
from asyncio import Queue, Task
from typing import Any, TypeVar, Callable, Coroutine

from loguru import logger

T = TypeVar("T")


async def _start_processor_worker(
    queue: Queue[Any | None],
    func: Callable[..., Coroutine[Any, Any, T]],
    results: list[T],
) -> None:
    while True:
        raw_params = await queue.get()
        try:
            if raw_params is None:
                return
            logger.debug(f"Processing {raw_params[0]}")
            results.append(await func(*raw_params))
        finally:
            queue.task_done()


async def process_in_queue(
    objects_to_process: list[Any],
    func: Callable[..., Coroutine[Any, Any, T]],
    *args: Any,
    concurrency: int = 50,
) -> list[T]:
    """
    This function executes multiple asynchronous tasks in a bounded way
    (e.g. having 200 tasks to execute, while running only 20 concurrently),
    to prevent overload and memory issues when dealing with large sets of data and tasks.

    Usage:
    ```python
    async def incrementBy(num: int, increment_by: int) -> int:
        await asyncio.sleep(3)
        return num + increment_by

    async def main():
        raw_objects = [1, 2, 3, 4, 5]
        processed_objects = await process_in_queue(
            raw_objects,
            incrementBy,
            5
        )
    ```

    :param objects_to_process: A list of the raw objects to process
    :param func: An async function that turns raw object into result object
    :param args: Static arguments to pass to the func when called
    :param concurrency: An integer specifying the concurrent workers count
    :return: A list of result objects
    """
    queue: Queue[Any | None] = Queue(maxsize=concurrency * 2)
    tasks: list[Task[Any]] = []
    processing_results: list[T] = []

    for i in range(concurrency):
        tasks.append(
            asyncio.create_task(
                _start_processor_worker(queue, func, processing_results)
            )
        )

    for i in range(len(objects_to_process)):
        await queue.put((objects_to_process[i], *args))

    for i in range(concurrency):
        # We put None value into the queue, so the workers will know that we
        # are done sending more input and they can terminate
        await queue.put(None)

    await queue.join()
    await asyncio.gather(*tasks)

    return processing_results