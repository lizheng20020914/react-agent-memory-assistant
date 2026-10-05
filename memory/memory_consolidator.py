"""
记忆压缩模块

用于在对话历史过长时进行摘要压缩，保持 Token 预算。
"""

import json
from pathlib import Path
from configs.setting import SESSION_DIR
import tiktoken

class MemoryConsolidator:
    """
    记忆压缩器。

    当对话历史超过 Token 预算时，将旧消息压缩为摘要，
    保留重要信息的同时减少 Token 消耗。
    """

    KEEP_LAST_MESSAGES = 2  # 保留最近的消息数

    def __init__(
        self,
        summary_model,
        session_id: str,
        session_dir: str = SESSION_DIR,
        token_budget: int = 1200,
        summary_target: int = 400
    ):
        """
        初始化记忆压缩器。
        """
        self.session_dir = Path(session_dir)
        self.token_budget = token_budget
        self.summary_file = self.session_dir / f"{session_id}_summary.json"
        self.summary_model = summary_model
        self.summary_target = summary_target

        self.session_dir.mkdir(
            parents=True,
            exist_ok=True
        )
        self.encoding = tiktoken.get_encoding("cl100k_base")


    def estimate_tokens(self, messages: list[dict]) -> int:
        """
        估算消息列表的 Token 数量。

        Args:
            prompt: 字符串消息

        Returns:
            估算的 Token 数量
        """
        total_string = ""

        for msg in messages:
        # 使用 ensure_ascii=False 支持中文
            total_string += json.dumps(msg, ensure_ascii=False)

        tokens = self.encoding.encode(total_string)

        # 安全余量
        return int(len(tokens) * 1.2)


    def _save_summary(self, summary: str, summarized_count: int) -> None:
        """
        将摘要保存到 HISTORY.json 文件。

        Args:
            summary: 摘要文本
            summarized_count: 已经被压缩的消息数量
        """ 
        content = {
            "summary": summary,
            "summarized_count": summarized_count
        }
        with self.summary_file.open("w",  encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)

  
    def _read_history(self) -> dict:
        """
        读取 HISTORY.json 文件。
        """ 
        if not self.summary_file.exists():
            return {
                "summary": "",
                "summarized_count": 0,
            }
    
        with self.summary_file.open("r",  encoding="utf-8") as f:
            return json.load(f)


    async def maybe_consolidate(self, messages: list[dict]) -> list[dict]:

        state = self._read_history()

        old_summary = state.get("summary")
        summarized_count = state.get("summarized_count", 0)

        # 如果消息被清空，summarized_count=0
        if summarized_count > len(messages):
            summarized_count = 0

            # 保留摘要，只重置压缩位置
            self._save_summary(
                summary=old_summary,
                summarized_count=0,
            )

        # 只取得尚未进入摘要的消息
        unsummarized = messages[summarized_count:]

        consolidated = []

        if old_summary:
            consolidated.append({
                "role": "system",
                "content": f"[历史摘要]\n{old_summary}",
            })

        consolidated.extend(unsummarized)

        # 没有超过预算
        if self.estimate_tokens(consolidated) <= self.token_budget:
            return consolidated

        # 最近6条保留原文
        pending_messages = unsummarized[-self.KEEP_LAST_MESSAGES:]

        # 其余尚未压缩的消息参与摘要
        messages_to_compress = unsummarized[:-self.KEEP_LAST_MESSAGES]

        if messages_to_compress:
            new_summary = await self._summarize(
                previous_summary=old_summary,
                messages=messages_to_compress,
            )

            summarized_count += len(messages_to_compress)
        else:
            # 没有旧消息可以继续压缩
            new_summary = old_summary

        self._save_summary(
                        summary=new_summary,
                        summarized_count=summarized_count,
                    )

        consolidated = []

        if new_summary:
            consolidated.append({
                "role": "system",
                "content": f"[历史摘要]\n{new_summary}",
            })

        consolidated.extend(pending_messages)

        # 压缩后再次检查,超了就截断summary
        if self.estimate_tokens(consolidated) > self.token_budget:
            overflow_tokens = self.estimate_tokens(consolidated) - self.token_budget
            new_summary_tokens = int(len(self.encoding.encode(new_summary)) * 1.2)
            truncate_target = new_summary_tokens - overflow_tokens - 50 # 安全余量

            if not new_summary or truncate_target < 0:
                raise ValueError(
                    "最近6条消息本身超过Token预算, 无法通过截断摘要解决" 
                )
            
            consolidated = self._truncate(
                consolidated,
                truncate_target,
            )
        
        return consolidated


    async def _summarize(self, previous_summary: str, messages: list[dict]) -> str:
        """
        使用 LLM 生成消息摘要。

        Args:
            summary_msg: 已经被压缩过的消息
            messages: 待压缩的消息列表

        Returns:
            摘要文本
        """

        conversation_parts = []
        # 拼接旧消息为文本
        if previous_summary:
            conversation_parts.append(
                f"[已有摘要]\n{previous_summary}"
            )

        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            conversation_parts.append(f"[{role}]\n{content}")

        conversation_text = "\n\n".join(conversation_parts)
        
        # 构造摘要请求
        summary_prompt = f"""请用 3-5 句话概括以下对话的关键信息，保留重要的事实和结论，省略过程细节和寒暄。只输出摘要，不要其他内容。
        对话内容：
        {conversation_text}
        新摘要必须比输入内容更精炼, 且不得超过{self.summary_target} tokens。"""

        response = await self.summary_model.ainvoke(summary_prompt)

        return response.content.strip()

        
    def _truncate(self, messages: list[dict], truncate_target: int) -> list[dict]:
        result = [msg.copy() for msg in messages]

        # 默认第1条是历史摘要
        summary_msg = result[0]
        summary_text = summary_msg["content"]

        token_ids = self.encoding.encode(summary_text)

        # 因为Qwen与cl100k_base存在误差，再留20%余量
        keep_tokens = int(truncate_target / 1.2)

        truncated_ids = token_ids[:keep_tokens]
        truncated_text = self.encoding.decode(truncated_ids)

        result[0]["content"] = truncated_text + "\n[摘要已截断]"

        return result        
    