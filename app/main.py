from fastapi import FastAPI

app = FastAPI(title="GG Calendar AI")

@app.get("/health")
def health():
    return {"status": "ok"}
