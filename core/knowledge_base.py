import os
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from config import DASHSCOPE_API_KEY, EMBEDDING_MODEL, SIMILARITY_THRESHOLD, RERANK_MODEL, RERANK_THRESHOLD

class KnowledgeBaseManager:
    def __init__(self, username, kb_path):
        self.username = username
        self.kb_path = kb_path
        
        os.environ.setdefault("OPENAI_API_KEY", os.getenv("DASHSCOPE_API_KEY", ""))
        os.environ.setdefault("OPENAI_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        
        self.embeddings = OpenAIEmbeddings(
            model=EMBEDDING_MODEL,
            check_embedding_ctx_length=False
        )
        
        self.vector_store = self._init_chroma(kb_path)
        
        self.metadata_file = kb_path.parent / "kb_metadata.json"
        self._load_metadata()
    
    def _init_chroma(self, kb_path):
        try:
            return Chroma(
                persist_directory=str(kb_path),
                embedding_function=self.embeddings
            )
        except Exception as e:
            print(f"ChromaDB 初始化失败: {e}")
            print("尝试清理损坏的索引文件并重建...")
            kb_path.mkdir(parents=True, exist_ok=True)
            for f in kb_path.iterdir():
                if f.name.startswith("hnsw") or f.name.endswith(".sqlite3"):
                    f.unlink()
            return Chroma(
                persist_directory=str(kb_path),
                embedding_function=self.embeddings
            )
    
    def _load_metadata(self):
        if self.metadata_file.exists():
            with open(self.metadata_file, "r", encoding="utf-8") as f:
                self.metadata = json.load(f)
        else:
            self.metadata = {"documents": []}
            self._save_metadata()
    
    def _save_metadata(self):
        with open(self.metadata_file, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)
    
    def add_documents(self, documents, source_name="text_input"):
        print(f"\n=== 添加文档到知识库 ===")
        print(f"来源: {source_name}")
        print(f"文档数量: {len(documents)}")
        
        for doc in documents:
            doc.metadata["user"] = self.username
            doc.metadata["source"] = source_name
        
        batch_size = 10
        all_ids = []
        total_batches = (len(documents) + batch_size - 1) // batch_size
        
        def _do_add():
            ids = []
            for i in range(0, len(documents), batch_size):
                batch = documents[i:i + batch_size]
                batch_num = i // batch_size + 1
                print(f"添加批次 {batch_num}/{total_batches}: {len(batch)} 个文档")
                batch_ids = self.vector_store.add_documents(batch)
                if batch_ids:
                    ids.extend(batch_ids)
                    print(f"  成功获取 {len(batch_ids)} 个ID")
            return ids
        
        try:
            all_ids = _do_add()
        except Exception as add_err:
            print(f"ChromaDB 写入失败: {add_err}")
            print("尝试重建向量数据库...")
            try:
                self._recover_chroma()
                self.vector_store = self._init_chroma(self.kb_path)
                all_ids = _do_add()
                print("重建后写入成功")
            except Exception as recover_err:
                print(f"重建失败: {recover_err}")
                raise recover_err
        
        try:
            if not all_ids:
                raise Exception("向量化失败，没有生成任何ID")
            
            self.metadata["documents"].append({
                "source": source_name,
                "count": len(documents),
                "ids": all_ids
            })
            self._save_metadata()
            
            print(f"成功添加 {len(documents)} 条文档，共 {len(all_ids)} 个向量")
            print(f"当前总文档数: {len(self.metadata['documents'])}")
            print(f"======================\n")
            
            return len(documents)
        except Exception as e:
            print(f"添加文档失败: {e}")
            if all_ids:
                self.metadata["documents"].append({
                    "source": source_name,
                    "count": len(documents),
                    "ids": all_ids
                })
                self._save_metadata()
            raise
    
    def _recover_chroma(self):
        kb_path = self.kb_path
        kb_path.mkdir(parents=True, exist_ok=True)
        for f in kb_path.iterdir():
            if f.name.startswith("hnsw") or f.name.endswith(".sqlite3") or f.name.endswith(".pickle"):
                if f.is_file():
                    f.unlink()
                elif f.is_dir():
                    import shutil
                    shutil.rmtree(f, ignore_errors=True)
    
    def _rerank(self, query, docs):
        """使用 DashScope Rerank API 对检索结果重排序"""
        if not docs:
            return []
        
        try:
            url = "https://dashscope.aliyuncs.com/compatible-mode/v1/rerank"
            headers = {
                "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
                "Content-Type": "application/json"
            }
            
            documents = [doc.page_content for doc in docs]
            
            payload = {
                "model": RERANK_MODEL,
                "query": query,
                "documents": documents,
                "top_n": len(documents)
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            reranked = result.get("results", [])
            
            reranked_docs = []
            for item in reranked:
                idx = item.get("index")
                score = item.get("relevance_score")
                if score >= RERANK_THRESHOLD:
                    reranked_docs.append((docs[idx], score))
            
            print(f"Rerank 后保留 {len(reranked_docs)} 条相关结果")
            return reranked_docs
            
        except Exception as e:
            print(f"Rerank 失败，降级使用原始结果: {e}")
            return [(doc, 1.0) for doc in docs]
    
    def query(self, question, k=3):
        print(f"\n=== 查询知识库 ===")
        print(f"问题: {question}")
        
        doc_count = self.vector_store._collection.count()
        print(f"知识库文档总数: {doc_count}")
        
        if doc_count == 0:
            print("知识库为空")
            print(f"===================\n")
            return []
        
        results = self.vector_store.similarity_search_with_score(
            question,
            k=k,
        )
        
        print(f"向量检索到 {len(results)} 条结果")
        for i, (doc, score) in enumerate(results):
            print(f"  结果{i+1}: 相似度分数={score:.4f}, 内容={doc.page_content[:80]}")
        
        if not results:
            print(f"===================\n")
            return []
        
        reranked = self._rerank(question, [doc for doc, _ in results])
        
        print(f"===================\n")
        
        return reranked
    
    def list_documents(self):
        return self.metadata["documents"]
    
    def delete_document(self, source_name):
        doc_entry = None
        for entry in self.metadata["documents"]:
            if entry["source"] == source_name:
                doc_entry = entry
                break
        
        if doc_entry:
            ids = doc_entry.get("ids", [])
            if ids:
                try:
                    self.vector_store.delete(ids=ids)
                except Exception as e:
                    print(f"删除向量数据时出错: {e}")
            
            self.metadata["documents"].remove(doc_entry)
            self._save_metadata()
            return True
        
        return False
    
    def get_document_count(self):
        return len(self.metadata["documents"])
