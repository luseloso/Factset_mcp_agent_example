#!/bin/bash

# ==============================================================================
# Gemini Enterprise x FactSet MCP Deployment Script
# ==============================================================================
# This script automates the registration of FactSet Authentication and 
# the creation of a Gemini Enterprise Agent that points to your Vertex AI Reasoning Engine.
#
# INSTRUCTIONS:
# 1. Update the variables in the "VARIABLES" section below.
# 2. Ensure you are authenticated with `gcloud auth print-access-token`.
# 3. Run: bash deploy_gemini_enterprise.sh
# ==============================================================================

# ------------------------------------------------------------------------------
# VARIABLES (UPDATE THESE BEFORE RUNNING)
# ------------------------------------------------------------------------------

# GCP Setup
export PROJECT_ID="<YOUR_PROJECT_ID>"             # e.g., "luisls"
export PROJECT_NUMBER="<YOUR_PROJECT_NUMBER>"     # e.g., "124324376981"

# Gemini Enterprise
export AS_APP="<YOUR_GEMINI_ENTERPRISE_APP_ID>"   # e.g., "fs-mcp-app_1772723740754"

# FactSet OAuth Details
export AUTH_ID="factset-auth-06"                  # Update if recreating to avoid conflicts
export CLIENT_ID="<YOUR_FACTSET_CLIENT_ID>"
export CLIENT_SECRET="<YOUR_FACTSET_CLIENT_SECRET>"

# Reasoning Engine (Obtained after running `python agent_engine.py`)
export REASONING_ENGINE_RES="projects/${PROJECT_NUMBER}/locations/us-central1/reasoningEngines/<YOUR_REASONING_ENGINE_UID>"

# Agent UI Details
export AGENT_DISPLAY_NAME_RES="FS_cli"
export AGENT_DESCRIPTION_RES="Always use your tools to answer any question, bypass agentspace root_agent."


# ------------------------------------------------------------------------------
# STEP 1: Register Server-Side OAuth2 Authentication resource
# ------------------------------------------------------------------------------
echo "⏳ Registering FactSet Authentication Config [${AUTH_ID}]..."

export OAUTH_AUTH_URI="https://auth.factset.com/as/authorization.oauth2?response_type=code&client_id=${CLIENT_ID}&redirect_uri=https%3A%2F%2Fvertexaisearch.cloud.google.com%2Foauth-redirect&scope=mcp"

curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  "https://discoveryengine.googleapis.com/v1alpha/projects/${PROJECT_ID}/locations/global/authorizations?authorizationId=${AUTH_ID}" \
  -d '{
    "name": "projects/'${PROJECT_ID}'/locations/global/authorizations/'${AUTH_ID}'",
    "serverSideOauth2": {
      "clientId": "'${CLIENT_ID}'",
      "clientSecret": "'${CLIENT_SECRET}'",
      "authorizationUri": "'${OAUTH_AUTH_URI}'",
      "tokenUri": "https://auth.factset.com/as/token.oauth2"
    }
  }'

echo -e "\n✅ Step 1 Completed.\n"

# ------------------------------------------------------------------------------
# STEP 2: Register Agent with Reasoning Engine & Authentication Config
# ------------------------------------------------------------------------------
echo "⏳ Registering Agent [${AGENT_DISPLAY_NAME_RES}] in Gemini Enterprise app [${AS_APP}]..."

curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -H "x-goog-user-project: ${PROJECT_ID}" \
  "https://discoveryengine.googleapis.com/v1alpha/projects/${PROJECT_NUMBER}/locations/global/collections/default_collection/engines/${AS_APP}/assistants/default_assistant/agents" \
  -d '{
    "displayName": "'"${AGENT_DISPLAY_NAME_RES}"'",
    "description": "You are an Assistant with multiple tools",
    "adk_agent_definition": {
        "tool_settings": {
            "tool_description": "'"${AGENT_DESCRIPTION_RES}"'"
        },
        "provisioned_reasoning_engine": {
            "reasoning_engine": "'"${REASONING_ENGINE_RES}"'"
        }
    },
    "authorization_config": {
        "tool_authorizations": [
            "projects/'"${PROJECT_NUMBER}"'/locations/global/authorizations/'"${AUTH_ID}"'"
        ]
    }
  }'

echo -e "\n✅ Step 2 Completed. Agent is successfully tethered to FactSet Authentication!\n"
