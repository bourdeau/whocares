from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

app = FastAPI()

UPLOAD_DIR = Path("/tmp/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/", response_class=PlainTextResponse)
def hello():
    return "Hello World"


@app.post("/upload")
async def upload(request: Request):
    data = await request.body()
    path = UPLOAD_DIR / f"{uuid4().hex}.bin"
    async with aiofiles.open(path, "wb") as f:
        await f.write(data)
    return {"path": str(path), "size": len(data)}
