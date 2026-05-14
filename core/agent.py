import os
import json
import re
import requests
from pathlib import Path
from typing import TypedDict
from openai import OpenAI, AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

from langgraph.graph import StateGraph, START, END
from config import DASHSCOPE_API_KEY, MODEL_NAME, SIMILARITY_THRESHOLD, MAX_KB_RESULTS, TAVILY_API_KEY, MAX_SEARCH_RESULTS, RERANK_THRESHOLD
from core.knowledge_base import KnowledgeBaseManager
from core.web_search import TavilySearch


class AgentState(TypedDict):
    question: str
    messages: list
    need_kb: bool
    need_search: bool
    search_query: str
    kb_results: list
    search_results: str


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

        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(AgentState)

        workflow.add_node("analyze", self._analyze_node)
        workflow.add_node("retrieve", self._retrieve_node)
        workflow.add_node("search", self._search_node)

        workflow.add_edge(START, "analyze")

        workflow.add_conditional_edges(
            "analyze",
            self._route_after_analyze,
            {
                "retrieve": "retrieve",
                "search": "search",
                "end": END,
            }
        )

        workflow.add_conditional_edges(
            "retrieve",
            self._route_after_retrieve,
            {
                "search": "search",
                "end": END,
            }
        )

        workflow.add_edge("search", END)

        return workflow.compile()

    def _analyze_node(self, state: AgentState) -> dict:
        question = state["question"]
        messages = state.get("messages", [])

        analyze_prompt = f"""你是一个智能助手的决策模块。你需要分析用户的问题，判断是否需要检索个人知识库和联网搜索。

判断规则：
- need_kb: 问题是否涉及用户的个人信息、之前上传的文档、个人知识？如果只是闲聊、问候，不需要检索知识库。
- need_search: 问题是否需要实时信息、最新数据、无法从知识库获取的外部信息？常见需要搜索的情况：询问当前时间、天气、新闻、最新事件、实时数据等。
- search_query: 如果需要搜索，生成一个优化的搜索查询词（简洁精确）。如果不需要搜索，留空字符串。

请严格以JSON格式返回，不要包含其他内容：
{{"need_kb": true/false, "need_search": true/false, "search_query": "..."}}

用户问题：{question}"""

        try:
            response = self.client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": analyze_prompt}],
                temperature=0.1,
                max_tokens=300
            )
            content = response.choices[0].message.content
            decision = self._parse_json(content)
        except Exception as e:
            print(f"决策分析失败，使用默认策略: {e}")
            decision = {"need_kb": True, "need_search": False, "search_query": ""}

        need_kb = decision.get("need_kb", True)
        need_search = decision.get("need_search", False)
        search_query = decision.get("search_query", question)

        if not self.searcher:
            need_search = False

        print(f"[决策] need_kb={need_kb}, need_search={need_search}, search_query={search_query}")

        return {
            "need_kb": need_kb,
            "need_search": need_search,
            "search_query": search_query,
        }

    def _parse_json(self, content: str) -> dict:
        content = content.strip()
        json_match = re.search(r'\{[^{}]*\}', content)
        if json_match:
            return json.loads(json_match.group())
        if content.startswith("{"):
            return json.loads(content)
        raise ValueError(f"无法解析JSON: {content}")

    def _route_after_analyze(self, state: AgentState) -> str:
        if state["need_kb"]:
            return "retrieve"
        elif state["need_search"]:
            return "search"
        else:
            return "end"

    def _route_after_retrieve(self, state: AgentState) -> str:
        if state["need_search"]:
            return "search"
        else:
            return "end"

    def _retrieve_node(self, state: AgentState) -> dict:
        question = state["question"]
        kb_results = self.kb_manager.query(question, k=MAX_KB_RESULTS)
        kb_results = self._filter_and_rerank(question, kb_results)

        print(f"[检索] 知识库返回 {len(kb_results)} 条相关结果")

        return {"kb_results": kb_results}

    def _search_node(self, state: AgentState) -> dict:
        search_query = state.get("search_query", state["question"])
        search_results = self._do_search(search_query)

        print(f"[搜索] 查询={search_query}, 结果长度={len(search_results) if search_results else 0}")

        return {"search_results": search_results or ""}

    def _filter_and_rerank(self, query: str, results: list) -> list:
        if not results:
            return []

        filtered = []
        for doc, score in results:
            similarity = 1.0 / (1.0 + score)
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

    def _build_messages(self, question: str, kb_results: list, search_results: str) -> list:
        has_relevant_kb = kb_results and len(kb_results) > 0
        has_search = bool(search_results and "未找到" not in search_results and "搜索失败" not in search_results)

        if has_relevant_kb and has_search:
            context = "\n".join([doc.page_content for doc, score in kb_results])
            system_prompt = f"""你是一个专业、友好的智能助手。你结合用户个人知识库和网络搜索结果来回答问题。

个人知识库相关内容：
{context}

网络搜索结果：
{search_results}

回答规则：
1. 优先结合知识库和网络搜索结果进行综合回答
2. 如果搜索结果与知识库内容矛盾，请说明差异
3. 如果两者都无法回答，请诚实告知用户你不知道
4. 不要编造信息

格式要求：
- 使用 Markdown 格式输出
- 合理使用标题、列表、加粗等排版元素
- 对于复杂的回答，分点分段，使用清晰的层级结构"""

        elif has_relevant_kb and not has_search:
            context = "\n".join([doc.page_content for doc, score in kb_results])
            system_prompt = f"""你是一个专业、友好的智能助手。以下是用户个人知识库中与问题相关的内容。

个人知识库相关内容：
{context}

回答规则：
1. 请基于个人知识库中的信息回答
2. 如果知识库信息不足，可以适当补充你自己的知识
3. 如果问题明显涉及用户个人信息而你也不知道，请诚实告知不知道
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
2. 如果搜索结果无法回答用户的问题，请诚实告知用户无法回答
3. 保持回答准确、友好、简洁
4. 不要编造信息

格式要求：
- 使用 Markdown 格式输出
- 合理使用标题、列表、加粗等排版元素"""

        else:
            system_prompt = """你是一个专业、友好的智能助手。

回答规则：
1. 你的个人知识库中没有相关信息，也不需要联网搜索
2. 对于通用知识（如科学、历史、技术、常识等），请用你自己的知识回答
3. 如果问题涉及用户的个人信息（如"我是谁"、"我的名字"等），你并不知道答案，请诚实地回答不知道
4. 不要编造信息

格式要求：
- 使用 Markdown 格式输出
- 合理使用标题、列表、加粗等排版元素
- 对于复杂的回答，分点分段，使用清晰的层级结构"""

        messages = [{"role": "system", "content": system_prompt}]

        for msg in self.conversation_history[-10:]:
            messages.append(msg)

        return messages

    def _run_workflow(self, question: str):
        history_messages = list(self.conversation_history[-6:])
        initial_state: AgentState = {
            "question": question,
            "messages": history_messages,
            "need_kb": False,
            "need_search": False,
            "search_query": "",
            "kb_results": [],
            "search_results": "",
        }
        return self.graph.invoke(initial_state)

    async def _run_workflow_async(self, question: str):
        history_messages = list(self.conversation_history[-6:])
        initial_state: AgentState = {
            "question": question,
            "messages": history_messages,
            "need_kb": False,
            "need_search": False,
            "search_query": "",
            "kb_results": [],
            "search_results": "",
        }
        return await self.graph.ainvoke(initial_state)

    def query(self, question: str):
        self.conversation_history.append({"role": "user", "content": question})

        state = self._run_workflow(question)

        kb_results = state.get("kb_results", [])
        search_results = state.get("search_results", "")

        has_relevant_kb = len(kb_results) > 0
        has_search = bool(search_results and "未找到" not in search_results and "搜索失败" not in search_results)

        messages = self._build_messages(question, kb_results, search_results)

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
            error_str = str(e)
            if "data_inspection_failed" in error_str:
                answer = "抱歉，我无法回答这个问题。作为一个人工智能助手，我不能生成或传播不当内容。如果您有其他问题，我很乐意为您提供帮助。"
                self.conversation_history.append({"role": "assistant", "content": answer})
                self.save_history()
                return answer, False
            error_msg = f"抱歉，AI服务暂时不可用，请稍后重试。错误信息：{str(e)}"
            return error_msg, False

    async def query_stream(self, question: str):
        self.conversation_history.append({"role": "user", "content": question})

        state = await self._run_workflow_async(question)

        kb_results = state.get("kb_results", [])
        search_results = state.get("search_results", "")

        has_relevant_kb = len(kb_results) > 0
        has_search = bool(search_results and "未找到" not in search_results and "搜索失败" not in search_results)

        messages = self._build_messages(question, kb_results, search_results)

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
            error_str = str(e)
            if "data_inspection_failed" in error_str:
                yield "抱歉，我无法回答这个问题。作为一个人工智能助手，我不能生成或传播不当内容。如果您有其他问题，我很乐意为您提供帮助。"
                yield False
                yield False
                return
            error_msg = f"抱歉，AI服务暂时不可用，请稍后重试。错误信息：{str(e)}"
            yield error_msg
            yield False
            yield False

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

    def clear_history(self):
        self.conversation_history = []
        if self.history_file.exists():
            try:
                self.history_file.unlink()
            except IOError:
                pass