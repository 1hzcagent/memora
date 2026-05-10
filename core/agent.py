import os
import asyncio
from openai import OpenAI, AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

from config import DASHSCOPE_API_KEY, MODEL_NAME, SIMILARITY_THRESHOLD, MAX_KB_RESULTS
from core.knowledge_base import KnowledgeBaseManager

class PersonalAgent:
    def __init__(self, username, kb_manager: KnowledgeBaseManager):
        self.username = username
        self.kb_manager = kb_manager
        
        api_key = os.getenv("DASHSCOPE_API_KEY", "")
        api_base = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        
        os.environ.setdefault("OPENAI_API_KEY", api_key)
        os.environ.setdefault("OPENAI_API_BASE", api_base)
        
        self.client = OpenAI(
            api_key=api_key,
            base_url=api_base,
            timeout=60.0
        )
        
        self.async_client = AsyncOpenAI(
            api_key=api_key,
            base_url=api_base,
            timeout=60.0
        )
        
        self.conversation_history = []
    
    def query(self, question):
        self.conversation_history.append({"role": "user", "content": question})
        
        kb_results = self.kb_manager.query(question, k=MAX_KB_RESULTS)
        
        if kb_results:
            context = "\n".join([doc.page_content for doc, score in kb_results])
            
            system_prompt = f"""你是一个智能助手。请基于用户的个人知识库内容回答问题。

个人知识库内容：
{context}

回答规则：
1. 优先使用个人知识库中的信息回答
2. 如果知识库中有相关信息，请基于这些信息回答，并说明来源
3. 如果知识库信息不够完善，可以补充你自己的知识
4. 保持回答准确、友好、简洁
5. 如果用户的问题与知识库完全无关，直接用你的知识回答"""
        else:
            system_prompt = """你是一个智能助手。用户的个人知识库中没有相关信息。

回答规则：
1. 使用你自己的知识回答用户的问题
2. 保持回答准确、友好、简洁
3. 如果问题很专业或不确定，可以提醒用户可以将相关信息添加到个人知识库"""
        
        messages = [{"role": "system", "content": system_prompt}]
        
        for msg in self.conversation_history[-10:]:
            messages.append(msg)
        
        try:
            response = self.client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                temperature=0.7,
                max_tokens=1000
            )
            
            answer = response.choices[0].message.content
            self.conversation_history.append({"role": "assistant", "content": answer})
            
            has_kb_info = len(kb_results) > 0
            
            return answer, has_kb_info
        except Exception as e:
            error_msg = f"抱歉，AI服务暂时不可用，请稍后重试。错误信息：{str(e)}"
            return error_msg, False
    
    async def query_stream(self, question):
        self.conversation_history.append({"role": "user", "content": question})
        
        kb_results = self.kb_manager.query(question, k=MAX_KB_RESULTS)
        
        if kb_results:
            context = "\n".join([doc.page_content for doc, score in kb_results])
            
            system_prompt = f"""你是一个智能助手。请基于用户的个人知识库内容回答问题。

个人知识库内容：
{context}

回答规则：
1. 优先使用个人知识库中的信息回答
2. 如果知识库中有相关信息，请基于这些信息回答，并说明来源
3. 如果知识库信息不够完善，可以补充你自己的知识
4. 保持回答准确、友好、简洁
5. 如果用户的问题与知识库完全无关，直接用你的知识回答"""
        else:
            system_prompt = """你是一个智能助手。用户的个人知识库中没有相关信息。

回答规则：
1. 使用你自己的知识回答用户的问题
2. 保持回答准确、友好、简洁
3. 如果问题很专业或不确定，可以提醒用户可以将相关信息添加到个人知识库"""
        
        messages = [{"role": "system", "content": system_prompt}]
        
        for msg in self.conversation_history[-10:]:
            messages.append(msg)
        
        full_answer = ""
        has_kb_info = len(kb_results) > 0
        
        try:
            response = await self.async_client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                temperature=0.7,
                max_tokens=1000,
                stream=True
            )
            
            async for chunk in response:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_answer += content
                    yield content
            
            self.conversation_history.append({"role": "assistant", "content": full_answer})
            yield has_kb_info
            
        except Exception as e:
            error_msg = f"抱歉，AI服务暂时不可用，请稍后重试。错误信息：{str(e)}"
            yield error_msg
            yield False
    
    def clear_history(self):
        self.conversation_history = []
