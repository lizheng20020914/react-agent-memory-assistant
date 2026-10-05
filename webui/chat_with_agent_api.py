# 定义后台 API 的 URL
import json
import requests

chat_with_agent_url = "http://127.0.0.1:6605/chat/agent_chat"
chat_url = "http://127.0.0.1:6605/chat/chat"

def chat_with_agent(prompt, history, sys_prompt, history_len, temperature, max_tokens, stream, session_id):
    # 构建文件和表单数据
    files = [('files', (open(file_path["path"], 'rb'))) for file_path in prompt["files"]]
    # 提取文件路径并拼接到 query 中
    query = f'{prompt["text"]}\n'
    # 构建请求数据
    data = {
        "query": query,
        "sys_prompt": sys_prompt,
        #"history_len": history_len,
        #"history": [str(h) for h in history],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "session_id": session_id,
    }

    # 发送请求到 FastAPI 后端
    try:
        response = requests.post(chat_with_agent_url, files=files, data=data, stream=True)
        if response.status_code == 200:
            chunks = ""
            if stream:
                for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
                    if chunk:
                        data = json.loads(chunk)
                        chunks += data.get('answer', '')
                        yield chunks

            else:
                for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
                    data = json.loads(chunk)
                    chunks += data.get('answer', '')

                yield chunks            

        else:
            yield "请求失败，请检查后台服务器是否正常运行。"
    except Exception as e:
        yield f"发生错误：{e}"
