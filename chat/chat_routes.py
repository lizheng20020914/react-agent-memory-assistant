import json
import asyncio
import os
from memory.session_manager import SessionManager
from memory.memory_consolidator import MemoryConsolidator
from fastapi import APIRouter, UploadFile, Form
from fastapi.responses import StreamingResponse
from tools.tools_select import tools
from typing import List, AsyncIterable
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain.agents import create_react_agent, AgentExecutor
from langchain.prompts import SystemMessagePromptTemplate, HumanMessagePromptTemplate
from configs.prompt import PROMPT_TEMPLATES
from configs.setting import chat_model_name, api_key, base_url, TIME_OUT, TEMP_FILE_STORAGE_DIR
from utils.callback import CustomAsyncIteratorCallbackHandler
from db_server.base import session
from db_server.knowledge_base_repository import list_kb_from_db
from tools.code_interpreter import code_interpreter
from utils.load_docs import get_file_content
from tools.save_memory import save_memory

# 初始化 FastAPI 应用
chat_router = APIRouter(prefix = "/chat", tags = ["Chat 对话"])

# 初始化memory manager
session_manager = SessionManager()

def files_rag(files, uuid):
    # 定义存储路径
    kb_file_storage_path = os.path.join(TEMP_FILE_STORAGE_DIR, uuid)
    # 确保存储目录存在
    os.makedirs(kb_file_storage_path, exist_ok=True)
    result = []

    if files:
        for file in  files:
            file_path = os.path.join(kb_file_storage_path, file.filename)

            # 保存文件到指定路径
            with open(file_path, "wb") as f:
                f.write(file.file.read())

    # 遍历目录中的所有文件并读取内容
    for filename in os.listdir(kb_file_storage_path):
        file_path = os.path.join(kb_file_storage_path, filename)

        if os.path.isfile(file_path):
            file_content = get_file_content(file_path)
            result.append(f"document: {file_path},\n content: {file_content}.\n")
            # 直接将路径和内容拼接到结果字符串
    return "".join(result)


@chat_router.post("/agent_chat")
async def agent_chat(
        files: List[UploadFile] = None,
        query: str = Form(..., description="用户输入"),
        sys_prompt: str = Form("You are a helpful assistant.", description="系统提示词"),
        # history_len: int | None = Form(None, description="保留历史消息的数量"),
        # history: List[str] = Form([], description="历史对话"),
        temperature: float = Form(0.5, description="LLM采样温度"),
        max_tokens: int = Form(1024, description="LLM最大token数配置"),
        session_id: str = Form(..., description="会话标识"),
):
    # 定义总结模型
    summary_model = ChatOpenAI(
        model=chat_model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
        max_tokens=400,
        streaming=False,
    )

    # 上下文压缩器
    memory_consolidator = MemoryConsolidator(
        summary_model=summary_model,
        token_budget=1200,
        session_id = session_id,
    )

    # 先读取旧历史
    stored_history = session_manager.get_history(
        session_id = session_id,
        limit = None
    )
    
    # 压缩历史信息
    compressed_history = await memory_consolidator.maybe_consolidate(stored_history)

    # 整合历史信息
    histories = "\n\n".join(
        f"{message.get('role', 'unknown')}:"
        f"{message.get('content', '')}"
        for message in compressed_history
    )

    # 保存用户询问
    session_manager.save_message(
        session_id, 
        {
            "role": "user",
            "content": query,            
        }
    )

    document = files_rag(files, session_id)
    
    async def agent_chat_iterator() -> AsyncIterable[str]:

        # 使用自己定义的回调处理函数
        callback = CustomAsyncIteratorCallbackHandler()
        callbacks = [callback]

        # 定义聊天模型
        chat_model = ChatOpenAI(
            model=chat_model_name,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=True,
            callbacks=callbacks
        )
        
        # 定义系统提示，用于设置行为规则
        system_message = SystemMessagePromptTemplate.from_template(sys_prompt)

        # 定义人类提示，用于用户输入
        human_message = HumanMessagePromptTemplate.from_template(PROMPT_TEMPLATES["agent"])

        # 组装成完整的 ChatPromptTemplate
        chat_prompt = ChatPromptTemplate.from_messages([system_message, human_message])

        # 创建代理
        agent = create_react_agent(chat_model, tools, chat_prompt, stop_sequence=["\nObserv"])
        agent_excutor = AgentExecutor(agent=agent, tools=tools, verbose = True)

        # 列出所有的知识库
        knowledgebases = list_kb_from_db(session)

        # 获取长期记忆
        long_term_memory = save_memory.get_memory()

        code_interpreter.output_files, code_interpreter.output_codes = "", ""

        kbs = ""
        # 整理成字符串
        for item in knowledgebases:
            kbs += f"{item['kb_name']}-{item['kb_info']}\n"

        # 开启异步任务执行agent
        agent_inputs = {
            "input": query,
            "history": histories,
            "knowledgebases": kbs,
            "documents": document,
            "long_term_memory": long_term_memory,
        }

        async def run_agent():
            try:
                # 超时必须包住真正的 Agent 执行过程
                return await asyncio.wait_for(
                    agent_excutor.ainvoke(agent_inputs),
                    timeout=TIME_OUT,
                )
            finally:
                # 正常结束、超时、异常都会通知流式迭代器退出
                callback.finish()

        task = asyncio.create_task(run_agent())

        answer_parts = []
        agent_result = None
        agent_error = None

        # 流式输出
        try:
            async for token in callback.aiter():
                response_data = {"answer": token}
                answer_parts.append(token)
                # 最后将输出文件列表发送
                yield json.dumps(response_data, ensure_ascii=False).encode("utf-8")
            agent_result = await task
        except asyncio.TimeoutError:
            agent_error = f"\n\n请求处理超时，请在 {TIME_OUT} 秒后重试。"
        except Exception as error:
            agent_error = f"\n\nAgent 执行失败：{error}"    
        finally:
            # 如果客户端中断连接，也取消后台 Agent
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True) 
        
        # 结果兜底
        if agent_error:
            answer_parts.append(agent_error)

            yield json.dumps(
                {"answer": agent_error},
                ensure_ascii=False,
            ).encode("utf-8")
        elif not "".join(answer_parts).strip():
            # 如果模型的输出格式变化，没有检测到 Final Answer，
            # 使用 AgentExecutor 的最终 output 兜底。
            fallback_answer = ""

            if isinstance(agent_result, dict):
                fallback_answer = agent_result.get("output", "")

            if fallback_answer:
                answer_parts.append(fallback_answer)

                yield json.dumps(
                    {"answer": fallback_answer},
                    ensure_ascii=False,
                ).encode("utf-8")


        # 如果有图片生成
        if code_interpreter.output_files:
            extra_answer = (
                f"\n\n{code_interpreter.output_codes}"
                f"\n\n![](http://localhost:6605"
                f"{code_interpreter.output_files})"
            )
        # 无图片，只有代码
        elif code_interpreter.output_codes:
            extra_answer = (f"\n\n{code_interpreter.output_codes}")
        # 没有生成代码
        else:
            extra_answer = ""

        final_answer = "".join(answer_parts) + extra_answer

        # 保存完整回答
        session_manager.save_message(
            session_id,
            {
                "role": "assistant",
                "content": final_answer,
            },
        )

        # 再发送额外内容
        if extra_answer:
            yield json.dumps({"answer": extra_answer} ,ensure_ascii=False).encode("utf-8")

    # 返回 StreamingResponse，以流的形式发送数据
    return StreamingResponse(agent_chat_iterator(), media_type="application/json")
