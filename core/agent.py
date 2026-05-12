import os
import json
import requests
from pathlib import Path
from openai import OpenAI, AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

from config import DASHSCOPE_API_KEY, MODEL_NAME, SIMILARITY_THRESHOLD, MAX_KB_RESULTS, TAVILY_API_KEY, MAX_SEARCH_RESULTS, RERANK_THRESHOLD
from core.knowledge_base import KnowledgeBaseManager
from core.web_search import TavilySearch

class PersonalAgent:
    def __init__(self, username, kb_manager: KnowledgeBaseManager):
        self.username = username
        self.kb_manager = kb_manager
        self.searcher = TavilySearch() if TAVILY_API_KEY else None

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

        self.user_data_dir = Path(kb_manager.kb_path).parent if hasattr(kb_manager, 'kb_path') else Path(f"user_data/{username}")
        self.history_file = self.user_data_dir / "chat_history.json"
        self.conversation_history = self.load_history()

    def load_history(self):
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return []
        return []

    def save_history(self):
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.conversation_history, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"Failed to save chat history: {e}")

    def _filter_and_rerank(self, query: str, results: list) -> list:
        if not results:
            return []

        filtered = []
        for doc, dist in results:
            similarity = 1.0 / (1.0 + dist)
            if similarity >= SIMILARITY_THRESHOLD:
                filtered.append((doc, similarity))

        if not filtered:
            print(f"所有结果相似度均低于阈值 {SIMILARITY_THRESHOLD}，知识库无相关结果")
            return []

        print(f"相似度过滤后保留 {len(filtered)} 条结果")

        try:
            url = "https://dashscope.aliyuncs.com/compatible-mode/v1/rerank"
            headers = {"Authorization": f"Bearer {DASHSCOPE_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": "gte-rerank",
                "query": query,
                "documents": [doc.page_content for doc, _ in filtered],
                "top_n": len(filtered)
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                reranked_items = data.get("results", [])
                reranked = [(filtered[item["index"]][0], item["relevance_score"]) for item in reranked_items]
                reranked.sort(key=lambda x: x[1], reverse=True)
                best_score = reranked[0][1] if reranked else 0
                print(f"Rerank 排序完成，最高分: {best_score}")
                return reranked
            else:
                print(f"Rerank API 返回错误: {resp.status_code}，降级使用相似度排序")
        except Exception as e:
            print(f"Rerank 失败: {e}，降级使用相似度排序")

        return sorted(filtered, key=lambda x: x[1], reverse=True)

    def _do_search(self, query: str) -> str:
        if not self.searcher:
            return ""
        print(f"自动触发搜索: {query}")
        result = self.searcher.search(query)
        return result

    def _need_search(self, question: str, kb_results: list) -> bool:
        has_kb = kb_results and len(kb_results) > 0

        realtime_keywords = ['今天', '现在', '当前', '最新', '最近', '实时', '新闻', '趋势', '排行榜', '天气', '几点', '几点钟', '当前时间', '现在时间', '时间是多少', '北京时间', '日期', '星期', '农历', '阳历']

        for keyword in realtime_keywords:
            if keyword in question:
                print(f"含实时关键词 '{keyword}'，触发搜索")
                return True

        if has_kb:
            print(f"知识库有相关结果且无需实时信息，跳过搜索")
            return False

        searchable_keywords = ['如何', '怎么', '为什么', '是什么', '2024', '2025', '2026', '今年', '本月', '本周', '刚刚']
        for keyword in searchable_keywords:
            if keyword in question:
                print(f"知识库无结果且含可搜索关键词 '{keyword}'，触发搜索")
                return True

        print(f"知识库无结果且无可搜索关键词，跳过搜索")
        return False

    def _build_messages(self, question, kb_results, search_results, has_relevant_kb, has_search):
        if has_relevant_kb and has_search:
            context = "\n".join([doc.page_content for doc, score in kb_results])
            system_prompt = f"""你是一个专业、友好的智能助手。用户的个人知识库中有与问题相关的内容，同时也有网络搜索到的实时信息。

个人知识库相关内容：
{context}

网络搜索结果：
{search_results}

回答规则：
1. 优先结合知识库和网络搜索结果回答
2. 如果搜索结果无法回答用户的问题，请基于知识库回答即可
3. 如果两者都无法回答，请诚实告知用户你不知道
4. 不要编造信息

格式要求：
- 使用 Markdown 格式输出
- 合理使用标题、列表、加粗等排版元素
- 对于复杂的回答，分点分段，使用清晰的层级结构"""

        elif has_relevant_kb and not has_search:
            context = "\n".join([doc.page_content for doc, score in kb_results])
            system_prompt = f"""你是一个专业、友好的智能助手。以下是用户的个人知识库中与问题相关的内容。

个人知识库相关内容：
{context}

回答规则：
1. 请基于个人知识库中的信息回答
2. 如果知识库信息不足，可以适当补充你自己的知识
3. 如果问题明显涉及用户的个人信息而你也不知道，请诚实告知不知道
4. 不要编造信息

格式要求：
- 使用 Markdown 格式输出
- 合理使用标题、列表、加粗等排版元素
- 对于复杂的回答，分点分段，使用清晰的层级结构"""

        elif not has_relevant_kb and has_search:
            system_prompt = f"""你是一个专业、友好的智能助手。以下是通过网络搜索获取的实时信息。

网络搜索结果：
{search_results}

回答规则：
1. 优先使用网络搜索结果中的信息回答
2. 如果搜索结果无法回答用户的问题，请诚实告知用户你无法回答，不要编造信息
3. 保持回答准确、友好、简洁

格式要求：
- 使用 Markdown 格式输出
- 合理使用标题、列表、加粗等排版元素
- 对于复杂的回答，分点分段，使用清晰的层级结构"""

        else:
            system_prompt = """你是一个专业、友好的智能助手。

回答规则：
1. 你的个人知识库中没有相关信息
2. 如果问题涉及用户的个人信息（如"我是谁"、"我的名字"、"我的信息"等），你并不知道答案，请诚实地回答不知道
3. 如果问题属于通用知识（如科学、历史、技术、常识等），请用你自己的知识回答
4. 不要编造信息，不确定时就如实说不知道

格式要求：
- 使用 Markdown 格式输出
- 合理使用标题、列表、加粗等排版元素
- 对于复杂的回答，分点分段，使用清晰的层级结构"""

        messages = [{"role": "system", "content": system_prompt}]

        for msg in self.conversation_history[-10:]:
            messages.append(msg)

        return messages

    def query(self, question):
        self.conversation_history.append({"role": "user", "content": question})

        kb_results = self.kb_manager.query(question, k=MAX_KB_RESULTS)
        kb_results = self._filter_and_rerank(question, kb_results)
        has_relevant_kb = len(kb_results) > 0

        search_results = None
        has_search = False

        if self._need_search(question, kb_results):
            search_results = self._do_search(question)
            has_search = bool(search_results and "未找到" not in search_results and "搜索失败" not in search_results)

        messages = self._build_messages(question, kb_results, search_results, has_relevant_kb, has_search)

        try:
            response = self.client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                temperature=0.7,
                max_tokens=8192
            )

            answer = response.choices[0].message.content

            self.conversation_history.append({"role": "assistant", "content": answer})
            self.save_history()

            return answer, has_relevant_kb or has_search
        except Exception as e:
            error_msg = f"抱歉，AI服务暂时不可用，请稍后重试。错误信息：{str(e)}"
            return error_msg, False

    async def query_stream(self, question):
        self.conversation_history.append({"role": "user", "content": question})

        kb_results = self.kb_manager.query(question, k=MAX_KB_RESULTS)
        kb_results = self._filter_and_rerank(question, kb_results)
        has_relevant_kb = len(kb_results) > 0

        search_results = None
        has_search = False

        if self._need_search(question, kb_results):
            search_results = self._do_search(question)
            has_search = bool(search_results and "未找到" not in search_results and "搜索失败" not in search_results)

        messages = self._build_messages(question, kb_results, search_results, has_relevant_kb, has_search)

        full_answer = ""

        try:
            response = await self.async_client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                temperature=0.7,
                max_tokens=8192,
                stream=True
            )

            async for chunk in response:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_answer += content
                    yield content

            self.conversation_history.append({"role": "assistant", "content": full_answer})
            self.save_history()
            yield has_relevant_kb
            yield has_search

        except Exception as e:
            error_msg = f"抱歉，AI服务暂时不可用，请稍后重试。错误信息：{str(e)}"
            yield error_msg
            yield False
            yield False

    def clear_history(self):
        self.conversation_history = []
        if self.history_file.exists():
            try:
                self.history_file.unlink()
            except IOError:
                pass