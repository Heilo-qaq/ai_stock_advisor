#!/bin/bash
# ============================================================
# AI智能选股顾问 - 一键部署脚本
# 适用于: Ubuntu 20.04+ / Debian 11+ / CentOS 8+
# 用法: bash deploy.sh
# ============================================================

set -e

echo "🧠 AI智能选股顾问 - 一键部署"
echo "================================"

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 检查Docker
if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}Docker未安装，正在安装...${NC}"
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    echo -e "${GREEN}Docker安装完成${NC}"
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${YELLOW}安装 docker-compose...${NC}"
    pip3 install docker-compose 2>/dev/null || \
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
        -o /usr/local/bin/docker-compose && chmod +x /usr/local/bin/docker-compose
fi

# 配置API Key
if [ ! -f .env ]; then
    echo ""
    read -p "请输入 DeepSeek API Key (可留空后续配置): " API_KEY
    echo "DEEPSEEK_API_KEY=${API_KEY:-your-api-key-here}" > .env
    echo -e "${GREEN}.env 文件已创建${NC}"
fi

# 构建并启动
echo ""
echo "📦 构建Docker镜像..."
docker-compose up -d --build

echo ""
echo -e "${GREEN}✅ 部署完成!${NC}"
echo ""

# 获取IP
SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
echo "================================"
echo -e "📱 手机访问地址: ${GREEN}http://${SERVER_IP}:8501${NC}"
echo ""
echo "常用命令:"
echo "  查看日志:  docker-compose logs -f"
echo "  重启服务:  docker-compose restart"
echo "  停止服务:  docker-compose down"
echo "  更新代码:  git pull && docker-compose up -d --build"
echo ""
echo "⚠️ 请确保云服务器安全组已开放 8501 端口"
echo "================================"
