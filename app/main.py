"""FastAPI 入口。

启动:uvicorn app.main:app --reload
"""
from __future__ import annotations

import logging

import threading

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.data_access import router as data_access_router
from app.api.governance import router as governance_router
from app.api.routes import router
from app.core.config import STATIC_DIR, settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)

logger = logging.getLogger("nl2sql")

app = FastAPI(title="NL2SQL", version="0.1.0")

app.include_router(router)
app.include_router(governance_router)
app.include_router(data_access_router)


@app.on_event("startup")
def _prewarm_retrievers() -> None:
    """启动后台预热检索器,消除各库首次查询的冷启动延迟。不阻塞启动(daemon 线程)。"""
    if not settings.prewarm_enabled:
        return

    def _run() -> None:
        try:
            from app.core.retrieval.pipeline import warm_all
            logger.info("检索器预热开始(后台)…")
            warm_all()
            logger.info("检索器预热结束")
        except Exception:
            logger.exception("检索器预热线程异常")

    threading.Thread(target=_run, daemon=True, name="retrieval-prewarm").start()

# 前端静态页挂在根路径,index.html 自动作为根。
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
