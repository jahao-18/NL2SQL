"""FastAPI 入口。

启动:uvicorn app.main:app --reload
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import STATIC_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)

app = FastAPI(title="NL2SQL", version="0.1.0")

app.include_router(router)

# 前端静态页挂在根路径,index.html 自动作为根。
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
