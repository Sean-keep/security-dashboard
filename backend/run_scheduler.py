#!/usr/bin/env python3
"""
独立调度器进程
运行方式: python run_scheduler.py
"""
import signal
import sys
import os
import time

# 添加 app 目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.scheduler_service import scheduler_service


# 主循环 tick。5 秒一轮是为了让「规则被改」的脏位尽快兑现 —— 以前 60 秒一轮，
# 新建规则最坏要等一分钟才挂上调度器。心跳仍然每个完整轮（60s）写一次，
# 避免把 system_config 刷成写热点。
TICK_SECONDS = 5
HEARTBEAT_EVERY_TICKS = 60 // TICK_SECONDS


def _handle_term(signum, _frame):
    """SIGTERM 来自 deploy.sh 的 kill。

    不装这个 handler 的话，进程被 kill 时 `stop()` 根本不会跑 —— APScheduler
    留下一堆没关的线程池 worker，容器里就变成「僵而不死」。
    """
    print(f"\n🛑 收到信号 {signum}，正在停止调度器...", flush=True)
    try:
        scheduler_service.stop()
    finally:
        print("👋 调度器已停止", flush=True)
        sys.exit(0)


def main():
    """启动调度器并保持运行"""
    signal.signal(signal.SIGTERM, _handle_term)
    signal.signal(signal.SIGINT, _handle_term)

    print("🚀 启动独立调度器进程...", flush=True)

    # 加载所有规则
    scheduler_service.load_all_rules()

    # 启动调度器
    scheduler_service.start()

    print(f"✅ 调度器已启动 (Running: {scheduler_service.scheduler.running})", flush=True)
    print(f"📋 当前任务数: {len(scheduler_service.scheduler.get_jobs())}", flush=True)

    ticks = 0
    try:
        while True:
            time.sleep(TICK_SECONDS)
            ticks += 1

            if not scheduler_service.scheduler.running:
                if ticks % HEARTBEAT_EVERY_TICKS == 0:
                    print("⚠️ 调度器已停止，正在重启...", flush=True)
                scheduler_service.load_all_rules()
                scheduler_service.start()
                continue

            # 脏位：规则表被 web 进程改过（新建/改周期/停用/删除），立刻对账。
            try:
                if scheduler_service.consume_dirty():
                    print("♻️ 规则表有变更，对账中...", flush=True)
                    scheduler_service.reconcile()
            except Exception as exc:
                print(f"⚠️ 对账失败: {exc}", flush=True)

            # 完整轮：写心跳 + 兜底全量对账。哪怕脏位丢了（比如 system_config
            # 那次写失败）也至少一分钟自愈一次。
            if ticks % HEARTBEAT_EVERY_TICKS == 0:
                scheduler_service.write_heartbeat()
                try:
                    scheduler_service.reconcile()
                except Exception as exc:
                    print(f"⚠️ 对账失败: {exc}", flush=True)
                jobs = scheduler_service.scheduler.get_jobs()
                if jobs:
                    next_run = jobs[0].next_run_time
                    print(f"✅ 调度器正常，{len(jobs)} 个任务，下次执行: {next_run}", flush=True)
                else:
                    print("⚠️ 调度器在跑，但一个任务都没有", flush=True)
    except (KeyboardInterrupt, SystemExit):
        # SIGTERM handler 里已经 exit 了；这里兜住 Ctrl-C / 外部 SystemExit
        pass
    finally:
        try:
            scheduler_service.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
