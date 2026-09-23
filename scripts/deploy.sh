#!/bin/bash
# Deploy into the running monolithic `security-dashboard-v2` container.
#
# 实测出来的布局（别猜，容器里跑的是 ubuntu:22.04 + mysqld + nginx + uvicorn +
# run_scheduler 四合一）：
#   后端  /opt/security-dashboard/backend   （自有 venv/、.env —— 两者都不许碰）
#   前端  /opt/security-dashboard/frontend/dist   ← 不在 backend 下！
#   nginx :80  ← 宿主 :8880     uvicorn :5000    mysql :3306 ← 宿主 :3307
#
# 两个反复踩到的坑，脚本里已经处理掉：
#   1. `docker cp src_dir DEST` 当 DEST 已存在时是**嵌套**成 DEST/src_dir，
#      不是合并。要合并必须写 `src_dir/.`。dist 也一样 —— 是合并不是替换，
#      旧的带 hash 的 chunk 会残留，必须先清空。
#   2. `pkill -f "uvicorn"` 会匹配到 docker exec 自己的命令行，把自己杀了
#      （exit 143）。必须按 PID。
#
# Usage:
#   ./scripts/deploy.sh              # backend + frontend
#   ./scripts/deploy.sh backend      # only backend
#   ./scripts/deploy.sh frontend     # only frontend (runs npm run build first)
#   ./scripts/deploy.sh migrate      # only run new SQL under backend/migrations
set -euo pipefail

CONTAINER="${CONTAINER:-security-dashboard-v2}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="/opt/security-dashboard/backend"
DIST="/opt/security-dashboard/frontend/dist"
WHAT="${1:-all}"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "❌ container '$CONTAINER' is not running" >&2
    exit 1
fi

# 按 PID 收拾，不用 pkill —— 见文件头第 2 条
stop_app() {
    docker exec "$CONTAINER" sh -c '
        for p in $(ps -eo pid,args | awk "/[r]un_scheduler.py|[u]vicorn app.main/ {print \$1}"); do
            kill "$p" 2>/dev/null || true
        done'
    sleep 2
}

start_app() {
    # 跟容器当前的启动命令保持一致：uvicorn 走 venv，调度器走系统 python3.10
    docker exec -d "$CONTAINER" sh -c \
        "cd $BACKEND && exec ./venv/bin/python3 ./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 5000 --workers 1 >> uvicorn.log 2>&1"
    docker exec -d "$CONTAINER" sh -c \
        "cd $BACKEND && exec /usr/bin/python3.10 -u run_scheduler.py >> scheduler.log 2>&1"
    sleep 5
}

push_backend() {
    echo "📦 backend → $CONTAINER:$BACKEND"
    # 绝对路径：docker cp 对相对路径的解析会随 cwd 漂
    # 注意 /. 后缀 —— 见文件头第 1 条
    docker cp "$ROOT/backend/app/api"      "$CONTAINER:$BACKEND/app/"
    docker cp "$ROOT/backend/app/core"     "$CONTAINER:$BACKEND/app/"
    docker cp "$ROOT/backend/app/models"   "$CONTAINER:$BACKEND/app/"
    docker cp "$ROOT/backend/app/schemas"  "$CONTAINER:$BACKEND/app/"
    docker cp "$ROOT/backend/app/services" "$CONTAINER:$BACKEND/app/"
    docker cp "$ROOT/backend/app/utils"    "$CONTAINER:$BACKEND/app/"
    docker cp "$ROOT/backend/app/main.py"  "$CONTAINER:$BACKEND/app/main.py"
    docker cp "$ROOT/backend/run_scheduler.py" "$CONTAINER:$BACKEND/run_scheduler.py"
    docker cp "$ROOT/backend/migrations/." "$CONTAINER:$BACKEND/migrations/"
    echo "✅ backend copied"
    echo "   未触碰：$BACKEND/.env（生产密钥）、$BACKEND/venv（容器自己的依赖）"
    echo "   未触碰：$BACKEND/app/data（容器自己的 sqlite 残留）"
}

push_frontend() {
    echo "🎨 building frontend…"
    (cd "$ROOT/frontend" && npm run build)
    echo "📦 frontend dist → $CONTAINER:$DIST"
    # 先清空再拷：dist/. 是合并，见文件头第 1 条
    docker exec "$CONTAINER" sh -c "rm -rf $DIST/*"
    docker cp "$ROOT/frontend/dist/." "$CONTAINER:$DIST/"
    echo "✅ frontend deployed ($(docker exec "$CONTAINER" sh -c "ls $DIST/assets | wc -l") assets)"
}

run_migrations() {
    echo "🛢  migrations"
    docker exec "$CONTAINER" sh -c "
        set -e
        cd $BACKEND
        set -a; . ./.env 2>/dev/null; set +a
        DB=\"\${MYSQL_DATABASE:-security_dashboard}\"
        U=\"\${MYSQL_USER:-root}\"
        for f in migrations/*.sql; do
            echo \"--- \$f\"
            MYSQL_PWD=\"\${MYSQL_PASSWORD}\" mysql -u\"\$U\" -h\"\${MYSQL_HOST:-127.0.0.1}\" \"\$DB\" < \"\$f\"
        done
        echo '✅ migrations applied (全部幂等，可重复跑)'
    "
}

check_health() {
    sleep 2
    if curl -fsS "http://localhost:8880/health" | grep -q healthy; then
        echo "✅ healthy: $(curl -fsS http://localhost:8880/health)"
    else
        echo "⚠️  /health 没报 healthy —— 看 docker logs $CONTAINER 或 $BACKEND/uvicorn.log" >&2
        return 1
    fi
}

case "$WHAT" in
    backend)  stop_app; push_backend; run_migrations; start_app; check_health ;;
    frontend) push_frontend; check_health ;;
    migrate)  stop_app; run_migrations; start_app; check_health ;;
    all)      stop_app; push_backend; push_frontend; run_migrations; start_app; check_health ;;
    *) echo "usage: $0 [backend|frontend|migrate|all]" >&2; exit 2 ;;
esac

echo "=== done ==="
echo "Web:  http://localhost:8880"
echo "API:  http://localhost:5000/api/docs"
