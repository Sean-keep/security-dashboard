#!/bin/bash
# 同时启动 Web 服务和调度器
# 注意：所有敏感配置通过环境变量传入，参考 .env.example

# 启动调度器（后台进程）
echo "Starting scheduler..."
python -u /app/run_scheduler.py >> /var/log/scheduler.log 2>&1 &
SCHEDULER_PID=$!
echo "Scheduler started (PID: $SCHEDULER_PID)"

# 等待调度器初始化
sleep 2
if [ -f /var/log/scheduler.log ]; then
    echo "Scheduler log:"
    cat /var/log/scheduler.log
fi

# 启动 Web 服务（前台进程）
echo "Starting web server..."
uvicorn app.main:app --host 0.0.0.0 --port 5000 --workers 1

# Web 服务退出后，终止调度器
kill $SCHEDULER_PID 2>/dev/null
