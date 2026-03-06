import vertexai
import os
from vertexai import agent_engines
from vertexai.preview.reasoning_engines import AdkApp
from dotenv import load_dotenv
from agent import root_agent


def deploy_agent_engine_app():
    # load_dotenv()
    GOOGLE_CLOUD_PROJECT = "luisls"
    GOOGLE_CLOUD_LOCATION = "us-central1"
    STAGING_BUCKET = "gs://factset-staging-v0"
    AGENT_DISPLAY_NAME = "Factset_MCP_Agent"

    vertexai.init(
        project=GOOGLE_CLOUD_PROJECT,
        location=GOOGLE_CLOUD_LOCATION,
        staging_bucket=STAGING_BUCKET,
    )

    app = AdkApp(
        agent=root_agent,
        enable_tracing=True,
    )

    # app.register_operations()

    with open("requirements.txt", "r") as file:
        reqs = file.read().splitlines()

    agent_config = {
        "agent_engine": app,
        "display_name": AGENT_DISPLAY_NAME,
        "requirements": reqs
        + [
            "google-cloud-aiplatform[agent_engines,adk]",
        ],
        "extra_packages": ["agent.py", "config.json"],
        "env_vars": {"GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true"},
    }

    existing_agents = list(agent_engines.list(filter='display_name="Factset_MCP_Agent"'))

    if existing_agents:
        print(
            f"Number of existing agents found for {AGENT_DISPLAY_NAME}:"
            + str(len(list(existing_agents)))
        )

    if existing_agents:
        # update the existing agent
        remote_app = existing_agents[0].update(**agent_config)
    else:
        # create a new agent
        remote_app = agent_engines.create(**agent_config)

    return None

if __name__ == "__main__":
    deploy_agent_engine_app()
