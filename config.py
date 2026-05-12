import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Project paths
BASE_DIR = Path(__file__).parent
USER_DATA_DIR = BASE_DIR / "user_data"
USER_DATA_DIR.mkdir(exist_ok=True)

# Model configuration
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
os.environ["OPENAI_API_KEY"] = DASHSCOPE_API_KEY
MODEL_NAME = os.getenv("MODEL_NAME", "qwen-plus")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v3")

# Retrieval settings
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", 0.3))
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 500))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 100))
MAX_KB_RESULTS = int(os.getenv("MAX_KB_RESULTS", 8))

# Rerank settings
RERANK_MODEL = os.getenv("RERANK_MODEL", "gte-rerank")
RERANK_THRESHOLD = float(os.getenv("RERANK_THRESHOLD", 0.5))

# Web search settings
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
MAX_SEARCH_RESULTS = int(os.getenv("MAX_SEARCH_RESULTS", 3))
