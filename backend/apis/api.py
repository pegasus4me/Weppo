from fastapi import FastAPI

app = FastAPI()

@app.post("/api/agent/send")