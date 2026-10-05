from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Dict, List, Literal, Union, cast

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult


class CustomAsyncIteratorCallbackHandler(AsyncCallbackHandler):
    """Callback handler that returns an async iterator."""

    queue: asyncio.Queue[str]

    done: asyncio.Event

    @property
    def always_verbose(self) -> bool:
        return True

    def __init__(self) -> None:
        # 初始化队列和事件
        self.queue = asyncio.Queue()
        self.done = asyncio.Event()

        # 初始化答案前缀和答案到达标志
        self.answer_prefix = "Final Answer:"
        self.answer_reached = False
        self.answer_buffer =""

    async def on_llm_start(
            self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> None:
        # If two calls are made in a row, this resets the state
        self.anwer_buffer = ""
        self.answer_reached = False #  将answer_reached设置为False
        # print(prompts)

    async def on_llm_new_token(self, token: str, **kwargs: Any) -> None:

        if not token:
            return
        if self.answer_reached:
            self.queue.put_nowait(token)
            return
        self.answer_buffer += token

        prefix_index = self.answer_buffer.find(
            self.answer_prefix
        )

        if prefix_index >= 0:
            self.answer_reached = True
            answer_start = prefix_index + len(self.answer_prefix)
            remaining_text = self.answer_buffer[answer_start:]
            self.answer_buffer = ""

            if remaining_text:
                self.queue.put_nowait(remaining_text)
        else:
            keep_length = len(self.answer_prefix) - 1
            self.answer_buffer = self.answer_buffer[-keep_length:]


    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        if self.answer_reached:
            self.done.set()

    async def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        self.done.set()

    async def aiter(self) -> AsyncIterator[str]:
        # done 设置后，仍然要输出队列里的剩余 Token
        while not self.done.is_set() or not self.queue.empty():
            try:
                token = await asyncio.wait_for(
                    self.queue.get(),
                    timeout=0.1,
                )
            except asyncio.TimeoutError:
                continue

            yield token

    def finish(self) -> None:
        """Agent 正常结束、超时或异常时，结束流式等待。"""
        self.done.set()
