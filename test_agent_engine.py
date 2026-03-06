import vertexai
import asyncio
import os
from fds.sdk.utils.authentication import ConfidentialClient

async def main():
    print("Minting test FactSet token...")
    
    # 1. Pull config.json and generate the FactSet token
    # Ensures the config is dynamically resolved relative to this script
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    try:
        fds_client = ConfidentialClient(config_path=config_path)
        test_token = fds_client.get_access_token()
        print("Successfully minted FactSet token.")
    except Exception as e:
        print(f"Failed to mint token: {e}")
        return
    print(f"Token Preview: {test_token}")
    # TODO: Update these with your details
    PROJECT_ID = "<YOUR_PROJECT_ID>" # e.g., "luisls"
    LOCATION = "<YOUR_LOCATION>" # e.g., "us-central1"
    TEST_USER_ID = "<YOUR_USER_ID>" # e.g., "jane.doe@factset.com"
    
    # After running `agent_engine.py`, copy the created Reasoning Engine Resource Name here.
    REASONING_ENGINE_ID = "<YOUR_REASONING_ENGINE_RESOURCE_NAME>" # e.g. "projects/123/locations/us-central1/reasoningEngines/456"

    # 2. Initialize Vertex client
    client = vertexai.Client(
        project=PROJECT_ID,
        location=LOCATION,
    )

    # 3. Get Deployed Agent Engine
    remote_agent = client.agent_engines.get(
        name=REASONING_ENGINE_ID
    )

    # 4. Inject token via 'state' during session creation
    # Agent Engine automatically wraps this state into the 'readonly_context' for your tools.
    try:
        session = await remote_agent.async_create_session(
            user_id=TEST_USER_ID,
            state={"test_auth_token": test_token} 
        )
        print(f"Session created: {session['id']}")
    except Exception as e:
        print(f"Failed to create session: {e}")
        return

    print("⏳ Streaming query to remote agent...\n")

    # 5. Stream the query (Do NOT pass readonly_context or state here)
    try:
        async for event in remote_agent.async_stream_query(
            user_id=TEST_USER_ID,
            session_id=session["id"],
            message="Can you tell me about the q1 2025 reporting for Apple?",
        ):
            print(event)
    except Exception as e:
        print(f"❌ Error during stream: {e}")

if __name__ == "__main__":
    asyncio.run(main())