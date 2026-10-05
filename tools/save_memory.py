# 保存长期记忆
import json
from pathlib import Path
from configs.setting import MEMORY_DIR
from pydantic import BaseModel, Field

class Memory(BaseModel):
    user_information: str | None = Field(
        default=None,
        description="用户信息",
    )
    technical_preferences: str | None = Field(
        default=None,
        description="技术偏好",
    )
    projects: str | None = Field(
        default=None,
        description="项目信息",
    )
    important_correction: str | None = Field(
        default=None,
        description="重要纠正",
    )
    other_long_term_information: str | None = Field(
        default=None,
        description="用户信息、技术偏好、项目信息、重要纠正 之外的长期记忆",
    )

class SaveMemory:
    def __init__(self, memory_path = MEMORY_DIR):
        self.memory_path = Path(memory_path)

        # 先创建 memory 目录
        self.memory_path.mkdir(
            parents=True,
            exist_ok=True,
        )
        # 暂时不用user id区分记忆
        self.memory_file = self.memory_path / "long_term_memory.md"

        # 创建长期记忆文件
        if not self.memory_file.exists():
            self.memory_file.write_text(
                "# Long-term Memory\n\n"
                "## 用户信息\n\n"
                "## 技术偏好\n\n"
                "## 当前项目\n\n"
                "## 重要纠正\n\n"
                "## 其他长期信息\n\n",
                encoding="utf-8",
            )        

    def _insert_memory(self, text: str, heading: str, content: str,) -> tuple[str, bool]:

        content = content.strip()
        new_item = f"- {content}"

        # 避免完全相同的记忆重复保存
        if new_item in text:
            return text, False

        lines = text.splitlines()

        try:
            heading_index = lines.index(heading)
        except ValueError:
            # 标题不存在时，在文件末尾创建
            lines.extend([
                "",
                heading,
                "",
                new_item,
            ])
            return "\n".join(lines).rstrip() + "\n", True

        # 跳过标题下面的空行
        insert_index = heading_index + 1

        while (
            insert_index < len(lines)
            and not lines[insert_index].strip()
        ):
            insert_index += 1

        # 插入到当前分类最前面
        lines.insert(insert_index, new_item)

        return "\n".join(lines).rstrip() + "\n", True

        
    def run(self, content: str) -> str:
        try:
            content_dict = json.loads(content)
        except json.JSONDecodeError:
            return "记忆保存失败：输入不是合法 JSON"

        try:
            validated_memory = Memory.model_validate(content_dict)
        except Exception as error:
            return f"记忆保存失败：{error}"

        field_to_heading = {
            "user_information": "## 用户信息",
            "technical_preferences": "## 技术偏好",
            "projects": "## 当前项目",
            "important_correction": "## 重要纠正",
            "other_long_term_information": "## 其他长期信息"
        }

        memory_text = self.memory_file.read_text(
            encoding="utf-8"
        )

        saved_categories = []

        for field_name, heading in field_to_heading.items():
            value = getattr(validated_memory, field_name)

            if not value:
                continue

            memory_text, saved = self._insert_memory(
                text=memory_text,
                heading=heading,
                content=value,
            )

            if saved:
                saved_categories.append(heading.removeprefix("## "))

        if not saved_categories:
            return "没有发现需要新增的长期记忆"

        self.memory_file.write_text(
            memory_text,
            encoding="utf-8",
        )

        return (
            "长期记忆保存成功，更新分类："
            + "、".join(saved_categories)
        )

    def get_memory(self) -> str:
        if not self.memory_file.exists():
            return ""

        return self.memory_file.read_text(
            encoding="utf-8"
        )


save_memory = SaveMemory()

