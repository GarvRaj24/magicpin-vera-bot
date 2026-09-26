"""
Start script for Vera Bot Server
================================
Run this to start your bot server on port 8080.
Exposes endpoints on http://localhost:8080/v1/...
"""

import os
import sys
import uvicorn

def main():
    port = int(os.environ.get("PORT", 8080))
    host = os.environ.get("HOST", "0.0.0.0")

    print("\n" + "="*65)
    print("      MAGICPIN AI CHALLENGE - VERA BOT SERVER")
    print("="*65)
    print(f"  • Host: {host}")
    print(f"  • Port: {port}")
    print(f"  • Health check:  http://localhost:{port}/v1/healthz")
    print(f"  • Bot Metadata:  http://localhost:{port}/v1/metadata")
    print(f"  • Context Push:  POST http://localhost:{port}/v1/context")
    print(f"  • Tick:          POST http://localhost:{port}/v1/tick")
    print(f"  • Reply:         POST http://localhost:{port}/v1/reply")
    print("="*65 + "\n")

    uvicorn.run("bot:app", host=host, port=port, reload=False)

if __name__ == "__main__":
    main()
