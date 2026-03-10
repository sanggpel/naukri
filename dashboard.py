"""Entry point for the web dashboard."""

import uvicorn
from dotenv import load_dotenv

load_dotenv()

from src.web.app import create_app

app = create_app()

if __name__ == "__main__":
    uvicorn.run("dashboard:app", host="127.0.0.1", port=8080, reload=True)
