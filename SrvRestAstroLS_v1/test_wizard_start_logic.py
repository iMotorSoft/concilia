import asyncio
import os
import sys
from pathlib import Path

# Setup paths
sys.path.append(os.getcwd())

from routes.v1.reconcile_wizard_start import reconcile_wizard_start
from litestar.testing import TestClient
from ls_iMotorSoft_Srv01 import app

async def main():
    with TestClient(app=app) as client:
        print("Sending request...")
        response = client.post("/api/reconcile_wizard/start", json={
            "bank": "fce",
            "account": "001",
            "dataset_ref": "mock"
        })
        print(f"Status: {response.status_code}")
        print(f"Body: {response.json()}")
        print("Waiting 3s for background task...")
        await asyncio.sleep(3)
        print("Done waiting.")

if __name__ == "__main__":
    asyncio.run(main())
