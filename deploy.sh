#!/bin/bash

echo "=========================================="
echo "  个人知识库Agent - Docker自动部署脚本"
echo "=========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 1. 检查Docker是否安装
echo -e "${YELLOW}[1/6] 检查Docker安装...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}错误：Docker未安装，请先安装Docker${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker已安装: $(docker --version)${NC}"
echo ""

# 2. 检查Docker Compose是否安装
echo -e "${YELLOW}[2/6] 检查Docker Compose安装...${NC}"
if ! docker compose version &> /dev/null; then
    echo -e "${RED}错误：Docker Compose未安装${NC}"
    echo "请运行: sudo apt-get install docker-compose-plugin"
    exit 1
fi
echo -e "${GREEN}✓ Docker Compose已安装${NC}"
echo ""

# 3. 创建必要的目录
echo -e "${YELLOW}[3/6] 创建数据目录...${NC}"
mkdir -p data
mkdir -p uploads
echo -e "${GREEN}✓ 目录创建完成${NC}"
echo ""

# 4. 检查.env文件
echo -e "${YELLOW}[4/6] 检查环境配置...${NC}"
if [ ! -f .env ]; then
    echo -e "${YELLOW}警告：.env文件不存在，从.env.example复制${NC}"
    if [ -f .env.example ]; then
        cp .env.example .env
        echo -e "${RED}请编辑.env文件，确保DASHSCOPE_API_KEY正确！${NC}"
        echo "编辑命令: nano .env"
        echo "按 Ctrl+X 保存退出"
        read -p "编辑完成后按回车继续..."
    else
        echo -e "${RED}错误：.env.example文件也不存在${NC}"
        exit 1
    fi
fi
echo -e "${GREEN}✓ 环境配置检查完成${NC}"
echo ""

# 5. 构建并启动Docker容器
echo -e "${YELLOW}[5/6] 构建Docker镜像并启动服务...${NC}"
docker compose down 2>/dev/null
docker compose up -d --build

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ 容器启动成功${NC}"
else
    echo -e "${RED}错误：容器启动失败${NC}"
    echo "请查看错误信息: docker compose logs"
    exit 1
fi
echo ""

# 6. 检查服务状态
echo -e "${YELLOW}[6/6] 检查服务状态...${NC}"
sleep 3
docker compose ps
echo ""

# 获取服务器IP
SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || echo "47.106.174.195")

echo "=========================================="
echo -e "${GREEN}部署完成！${NC}"
echo "=========================================="
echo ""
echo "访问地址: http://${SERVER_IP}:8000"
echo ""
echo "常用管理命令:"
echo "  查看日志: docker compose logs -f"
echo "  重启服务: docker compose restart"
echo "  停止服务: docker compose down"
echo "  更新部署: docker compose up -d --build"
echo ""
echo "防火墙提醒:"
echo "  请在服务器控制台开放端口 8000 (TCP)"
echo "=========================================="
