import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from config import DASHSCOPE_API_KEY, EMBEDDING_MODEL, SIMILARITY_THRESHOLD

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
        
        self.vector_store = Chroma(
            persist_directory=str(kb_path),
            embedding_function=self.embeddings
        )
        
        self.metadata_file = kb_path.parent / "kb_metadata.json"
        self._load_metadata()
    
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
        
        try:
            for i in range(0, len(documents), batch_size):
                batch = documents[i:i + batch_size]
                batch_num = i // batch_size + 1
                print(f"添加批次 {batch_num}/{total_batches}: {len(batch)} 个文档")
                
                batch_ids = self.vector_store.add_documents(batch)
                if batch_ids:
                    all_ids.extend(batch_ids)
                    print(f"  成功获取 {len(batch_ids)} 个ID")
            
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
            print(f"已保存 {len(all_ids)} 个ID到元数据")
            if all_ids:
                self.metadata["documents"].append({
                    "source": source_name,
                    "count": len(documents),
                    "ids": all_ids
                })
                self._save_metadata()
            raise
    
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
        
        print(f"检索到 {len(results)} 条结果")
        for i, (doc, score) in enumerate(results):
            print(f"  结果{i+1}: 分数={score:.4f}, 内容={doc.page_content[:80]}")
        
        max_threshold = 1.0
        
        relevant_results = [
            (doc, score) for doc, score in results 
            if score < max_threshold
        ]
        
        print(f"过滤后相关结果: {len(relevant_results)} 条")
        
        if not relevant_results and results:
            relevant_results = results
            print("使用全部结果（无过滤）")
        
        print(f"===================\n")
        
        return relevant_results
    
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
