from tavily import TavilyClient
from config import TAVILY_API_KEY, MAX_SEARCH_RESULTS

class TavilySearch:
    def __init__(self):
        self.client = TavilyClient(api_key=TAVILY_API_KEY) if TAVILY_API_KEY else None
    
    def search(self, query: str) -> str:
        """搜索网络并返回格式化结果"""
        if not self.client:
            return "搜索功能未配置 API Key"
        
        try:
            response = self.client.search(
                query=query,
                search_depth="advanced",
                max_results=MAX_SEARCH_RESULTS
            )
            
            results = response.get("results", [])
            if not results:
                return "未找到相关搜索结果"
            
            formatted = []
            for i, result in enumerate(results, 1):
                title = result.get("title", "")
                content = result.get("content", "")
                url = result.get("url", "")
                formatted.append(f"[{i}] {title}\n{content}\n来源: {url}")
            
            return "\n\n".join(formatted)
            
        except Exception as e:
            return f"搜索失败: {str(e)}"
