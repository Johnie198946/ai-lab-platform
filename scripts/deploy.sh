#!/usr/bin/env bash
# AI Lab Platform — 服务器端一键部署脚本
# 用法（在服务器上，仓库根目录）:
#   bash scripts/deploy.sh
#
# 前置: Docker + docker compose plugin 已安装（本脚本会自动检查/提示）
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> [1/4] 检查 Docker"
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: 未安装 Docker。请先执行:"
  echo "  dnf install -y dnf-utils && dnf config-manager --add-repo https://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo"
  echo "  dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin && systemctl enable --now docker"
  exit 1
fi
docker info >/dev/null 2>&1 || { echo "ERROR: Docker 未运行 (systemctl start docker)"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "ERROR: 缺少 docker compose plugin"; exit 1; }

echo "==> [2/4] 环境变量"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "   已从 .env.example 生成 .env —— 请修改数据库密码后重新运行"
  exit 1
fi

echo "==> [3/4] 构建并启动"
docker compose up -d --build

echo "==> [4/4] 等待健康检查"
for i in $(seq 1 30); do
  status=$(curl -sf http://127.0.0.1:8000/health || true)
  if [ -n "$status" ]; then
    echo "   API 就绪: $status"
    exit 0
  fi
  sleep 2
done
echo "WARN: 30 秒内未就绪，请查看日志: docker compose logs api"
exit 1
