import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    
    print(f"\n================ STARTING FASTAPI REST SERVER ================")
    print(f" Listening Host: http://{host}:{port}")
    print(f" Swagger Docs:   http://127.0.0.1:{port}/docs")
    print(f" OpenAPI JSON:   http://127.0.0.1:{port}/openapi.json")
    print(f" CORS Origins:   {os.getenv('CORS_ORIGINS')}")
    print(f" Mode:           STRICTLY READ-ONLY")
    print(f"==============================================================\n")
    
    uvicorn.run("api.main:app", host=host, port=port, reload=False)
