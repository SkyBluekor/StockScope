from fastapi import FastAPI


app = FastAPI(
    title="StockScope API",
    description="StockScope 투자 분석 및 시뮬레이션 API",
    version="0.1.0",
)


@app.get("/")
async def root():
    return {
        "service": "StockScope API",
        "status": "running",
    }


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
    }