import asyncio
import json
import httpx

async def main():
    async with httpx.AsyncClient() as client:
        # Create a new session
        try:
            response = await client.post("http://127.0.0.1:8000/apps/app/users/user/sessions", json={})
            session_id = response.json().get("session_id")
        except httpx.ConnectError:
            print("Failed to connect to 8000. Start the server first.")
            return
            
        print("Session ID:", session_id)
        
        # Send an event
        payload = {
            "session_id": session_id,
            "inputs": {"animal": "elephant", "location": "sector 9"},
            "user_id": "user",
            "app_name": "app"
        }
        
        # Using the standard /run_sse endpoint ADK UI uses
        print("Sending run_sse...")
        response = await client.post(
            "http://127.0.0.1:8000/run_sse", 
            json=payload,
            timeout=10.0
        )
        print("Response:", response.status_code)
        print("Text:")
        for line in response.text.split("\n"):
            print(line)

if __name__ == "__main__":
    asyncio.run(main())
