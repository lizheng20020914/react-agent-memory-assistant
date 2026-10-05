from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).resolve().parent.parent

chat_model_name = "Qwen/Qwen2.5-72B-Instruct"
api_key = os.getenv("SILICONFLOW_API_KEY")
base_url = "https://api.siliconflow.cn/v1"

embedding_model_path = "personal_space/AI_learning/Model/bge-large-zh-v1.5"

# 存储数据库的路径
KB_DIR = PROJECT_ROOT /"knowledgebases"
TEMP_KB_DIR = PROJECT_ROOT /"temp/knowledgebases"

# 存储文件的路径
FILE_STORAGE_DIR = PROJECT_ROOT /"data"
TEMP_FILE_STORAGE_DIR = PROJECT_ROOT /"temp/data"

# 知识库信息数据库的路径
SQLALCHEMY_DATABASE = PROJECT_ROOT /"db_server/data/"
DATABASE_FILE = (
    SQLALCHEMY_DATABASE / "info.db"
).resolve()
# 知识库信息数据库的URI
SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATABASE_FILE.as_posix()}"


# 设置超时
TIME_OUT = 120

# 媒体文件保存路径
MEDIA_DIR = PROJECT_ROOT /"temp/medias"

# 存放短期记忆的路径
SESSION_DIR = PROJECT_ROOT / "memory" / "sessions"

# 存放短期记忆的路径
MEMORY_DIR = PROJECT_ROOT / "memory" / "long_term memory"