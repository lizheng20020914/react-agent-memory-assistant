from configs.setting import SESSION_DIR
from pathlib import Path
from datetime import datetime, timezone
import json
from collections import deque

class SessionManager:
    def __init__(self, session_dir = SESSION_DIR):
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(
            parents=True,
            exist_ok=True
        )


    # 获取当前session的路径
    def _get_session_path(self, session_id: str) -> Path:
        return self.session_dir / f"{session_id}.jsonl"

    
    # 保存历史对话，包括agent思考过程和工具调用记录
    def save_message(self, session_id: str, message: dict) -> None:
        jsonl_path = self._get_session_path(session_id)

        record = message.copy()
        record["timestamp"] = datetime.now(timezone.utc).isoformat()
        
        # "a" 是追加模式：文件存在：在末尾追加。文件不存在：自动创建文件。
        with jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False,) + "\n") # 让中文以中文的方式写入jsonl            
            

    # 获取limit条历史记录
    def get_history(self, session_id: str, limit: int | None = None) -> list[dict]:
        jsonl_path = self._get_session_path(session_id)
        
        # 如果还没有jsonl，返回空历史
        if not jsonl_path.exists():
            return []
        
        history = []
        with jsonl_path.open("r", encoding="utf-8") as f:
            # 注意lines是遍历生成器（），不是列表[]
            lines = (line for line in f if line.strip())  
            if limit is None:
                lines = list(lines)
            else:
                lines = deque(lines, maxlen=limit)            

        for line in lines:
            line = json.loads(line)
            line.pop("timestamp", None)
            history.append(line)

        return history


    # 清空当前jsonl内容
    def clear(self, session_id: str) -> None:
        jsonl_path = self._get_session_path(session_id)

        if jsonl_path.exists():
            jsonl_path.unlink()


    # 列举session文件夹下所有 jsonl文件
    def list_sessions(self) -> list[str]:
        files = list(self.session_dir.glob("*.jsonl"))
        
        # 按照日期排序
        files.sort(
            key=lambda path: path.stat().st_mtime,
            reverse=True
        )
        
        return [path.stem for path in files]
    