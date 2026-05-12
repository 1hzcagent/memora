#!/bin/bash

set -e

echo "=========================================="
echo "🚀 开始更新部署..."
echo "=========================================="
echo ""

# 获取脚本所在目录作为项目根目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "📁 项目目录：$SCRIPT_DIR"
echo ""

# 检测 Docker Compose 命令（兼容 v1/v2）
if command -v docker &>/dev/null && docker compose version &>/dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
elif command -v docker-compose &>/dev/null; then
    DOCKER_COMPOSE="docker-compose"
else
    echo "❌ 错误：未找到 docker compose 或 docker-compose 命令！"
    echo "请安装 Docker 或 docker-compose"
    exit 1
fi
echo "🐳 使用 Docker Compose 命令：$DOCKER_COMPOSE"
echo ""

# 1. 检查 Git 仓库
echo "🔍 检查 Git 仓库状态..."
if [ ! -d ".git" ]; then
    echo "❌ 错误：当前目录不是 Git 仓库！"
    echo "请运行以下命令初始化："
    echo "    git init"
    echo "    git remote add origin https://github.com/1hzcagent/memora"
    exit 1
fi

# 检查远程仓库
REMOTE_URL=$(git remote get-url origin 2>/dev/null || echo "")
if [[ "$REMOTE_URL" != *"1hzcagent/memora"* ]]; then
    echo "⚠️  警告：远程仓库地址不匹配"
    echo "当前远程地址：$REMOTE_URL"
    echo "预期地址：https://github.com/1hzcagent/memora"
    echo ""
    read -p "是否修改远程仓库地址？(Y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]] || [ -z "$REPLY" ]; then
        git remote set-url origin https://github.com/1hzcagent/memora
        echo "✅ 远程仓库地址已更新"
    fi
fi

# 2. 拉取最新代码
echo "📦 从 GitHub 拉取最新代码 (https://github.com/1hzcagent/memora)..."
git fetch origin

# 获取当前分支
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "📍 当前分支：$CURRENT_BRANCH"

# 拉取代码（使用 rebase 保持提交历史干净）
git pull --rebase origin "$CURRENT_BRANCH" || {
    echo "⚠️  Git pull 失败，尝试重置到远程分支..."
    git reset --hard "origin/$CURRENT_BRANCH"
}

echo "✅ 代码已更新到最新版本"
git log -1 --oneline
echo ""

# 3. 停止旧容器
echo "⏹️  停止旧容器..."
if $DOCKER_COMPOSE ps | grep -q "Up"; then
    $DOCKER_COMPOSE down
    echo "✅ 旧容器已停止"
else
    echo "ℹ️  没有运行中的容器，跳过停止步骤"
fi
echo ""

# 4. 重新构建镜像
echo "🔨 重新构建 Docker 镜像..."
$DOCKER_COMPOSE build --no-cache
echo "✅ 镜像构建完成"
echo ""

# 5. 启动新容器
echo "▶️  启动新容器..."
$DOCKER_COMPOSE up -d
echo "✅ 容器已启动"
echo ""

# 6. 等待服务启动
echo "⏳ 等待服务启动..."
sleep 5

# 7. 检查容器状态
echo "🔍 检查容器状态..."
$DOCKER_COMPOSE ps
echo ""

# 8. 清理悬空镜像
echo "🧹 清理悬空镜像..."
docker image prune -f
echo "✅ 清理完成"
echo ""

# 9. 显示部署信息
echo "=========================================="
echo "✅ 部署完成！"
echo "=========================================="
echo ""
echo "📋 查看实时日志：$DOCKER_COMPOSE logs -f"
echo "🌐 访问应用：http://localhost:8000"
echo "📚 API 文档：http://localhost:8000/docs"
echo ""

# 10. 询问是否查看日志
read -p "是否查看实时日志？(Y/n): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]] || [ -z "$REPLY" ]; then
    $DOCKER_COMPOSE logs -f
fi
