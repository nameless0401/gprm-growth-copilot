import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .db import Base, engine
from .seed import seed
from .routes import meta, telegram, admin
from .services.scheduler import scheduler_loop

# Deployment marker: ensures Railway rebuilds from the current GitHub HEAD.


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    seed()
    task = asyncio.create_task(scheduler_loop())
    yield
    task.cancel()


app = FastAPI(title="GPRM Growth Copilot", version="0.1.2", lifespan=lifespan)
app.include_router(meta.router)
app.include_router(telegram.router)
app.include_router(admin.router)


@app.get("/health")
def health():
    return {"ok": True, "service": "gprm-growth-copilot", "version": "0.1.2"}
