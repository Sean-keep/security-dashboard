#!/usr/bin/env python3
"""
独立调度器进程
运行方式: python run_scheduler.py
"""
import time
import sys
import os

# 添加 app 目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.scheduler_service import scheduler_service

def main():
    """启动调度器并保持运行"""
    print("🚀 启动独立调度器进程...", flush=True)
    
    # 加载所有规则
    scheduler_service.load_all_rules()
    
    # 启动调度器
    scheduler_service.start()
    
    print(f"✅ 调度器已启动 (Running: {scheduler_service.scheduler.running})", flush=True)
    print(f"📋 当前任务数: {len(scheduler_service.scheduler.get_jobs())}", flush=True)
    
    # 保持进程运行
    try:
        while True:
            time.sleep(60)
            # 每分钟检查一次调度器状态
            if not scheduler_service.scheduler.running:
                print("⚠️ 调度器已停止，正在重启...")
                scheduler_service.load_all_rules()
                scheduler_service.start()
            else:
                jobs = scheduler_service.scheduler.get_jobs()
                if jobs:
                    next_run = jobs[0].next_run_time
                    print(f"✅ 调度器正常，下次执行: {next_run}")
    except KeyboardInterrupt:
        print("\n🛑 收到中断信号，正在停止调度器...")
        scheduler_service.stop()
        print("👋 调度器已停止")

if __name__ == "__main__":
    main()
