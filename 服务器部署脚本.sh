#!/bin/bash
# ============================================
# 个人知识库Agent - 一键部署脚本
# 在服务器"命令助手"中直接执行此脚本
# ============================================

echo "=========================================="
echo "  开始部署个人知识库Agent..."
echo "=========================================="
echo ""

# 创建项目目录
echo "[1/8] 创建项目目录..."
mkdir -p /opt/Customer_agent
cd /opt/Customer_agent

# 创建Dockerfile
echo "[2/8] 创建Dockerfile..."
cat > Dockerfile << 'DOCKERFILE_EOF'
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
DOCKERFILE_EOF

# 创建docker-compose.yml
echo "[3/8] 创建docker-compose.yml..."
cat > docker-compose.yml << 'COMPOSE_EOF'
version: '3.8'

services:
  agent:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY}
      - OPENAI_API_KEY=${DASHSCOPE_API_KEY}
    volumes:
      - ./data:/app/data
      - ./uploads:/app/uploads
    restart: unless-stopped

networks:
  agent-network:
    driver: bridge
COMPOSE_EOF

# 创建.env文件（包含您的API密钥）
echo "[4/8] 创建环境配置文件..."
cat > .env << 'ENV_EOF'
DASHSCOPE_API_KEY=sk-6a0ba449c1d8483180a606f2c5bc8662
ENV_EOF

# 创建requirements.txt
echo "[5/8] 创建requirements.txt..."
cat > requirements.txt << 'REQ_EOF'
streamlit>=1.30.0
langchain>=0.2.0
langchain-community>=0.2.0
langchain-chroma>=0.1.0
langchain-openai>=0.1.0
chromadb>=0.4.0
python-dotenv>=1.0.0
PyPDF2>=3.0.0
python-docx>=1.1.0
docx2txt>=0.8
openpyxl>=3.1.0
cryptography>=41.0.0
tiktoken>=0.5.0
fastapi>=0.100.0
uvicorn>=0.23.0
python-multipart>=0.0.6
REQ_EOF

# 创建数据目录
echo "[6/8] 创建数据目录..."
mkdir -p data uploads

# 创建前端文件目录结构
echo "[7/8] 创建前端文件..."
mkdir -p static

# 构建并启动Docker容器
echo "[8/8] 构建Docker镜像并启动服务..."
docker compose down 2>/dev/null || true
docker compose up -d --build

echo ""
echo "=========================================="
echo "  部署完成！"
echo "=========================================="
echo ""
echo "访问地址: http://47.106.174.195:8000"
echo ""
echo "查看日志: docker compose logs -f"
echo "检查状态: docker compose ps"
echo ""
