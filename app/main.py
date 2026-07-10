"""FastAPI 入口。

启动:uvicorn app.main:app --reload
"""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.data_access import router as data_access_router
from app.api.governance import router as governance_router
from app.api.routes import router
from app.core.config import STATIC_DIR, settings
from app.core.business_domains import AuthenticationError, AuthorizationError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)

logger = logging.getLogger("nl2sql")

@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.prewarm_enabled:
        def _run() -> None:
            try:
                from app.core.retrieval.pipeline import warm_all
                logger.info("检索器预热开始(后台)…")
                warm_all()
                logger.info("检索器预热结束")
            except Exception:
                logger.exception("检索器预热线程异常")

        threading.Thread(target=_run, daemon=True, name="retrieval-prewarm").start()
    yield


app = FastAPI(title="NL2SQL", version="0.1.0", lifespan=lifespan)


@app.exception_handler(AuthenticationError)
def _authentication_error(_: Request, exc: AuthenticationError) -> JSONResponse:
    return JSONResponse(status_code=401, content={"detail": str(exc)})


@app.exception_handler(AuthorizationError)
def _authorization_error(_: Request, exc: AuthorizationError) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(exc)})

app.include_router(router)
app.include_router(governance_router)
app.include_router(data_access_router)

# 前端静态页挂在根路径,index.html 自动作为根。
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
