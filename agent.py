import json
import os
import copy
import asyncio
from typing import Dict, Any, List, Optional
from fds.sdk.utils.authentication import ConfidentialClient

from google.adk.agents.llm_agent import LlmAgent
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPServerParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.adk.tools.mcp_tool.mcp_tool import MCPTool
from google.adk.tools.mcp_tool.mcp_session_manager import retry_on_errors
from google.adk.tools.openapi_tool.auth.auth_helpers import token_to_scheme_credential
from google.adk.agents.readonly_context import ReadonlyContext

# ---------------------------------------------------------------------------
# 1. RUNTIME AUTH: User-Delegated Pass-Through
# ---------------------------------------------------------------------------
def get_factset_headers(readonly_context: Any = None) -> Dict[str, str]:
    if not readonly_context:
        print("Security Warning: No user context provided. Denying access.")
        return {}

    user_token = None

    print(f"DEBUG READONLY_CONTEXT: {dir(readonly_context)}", flush=True)

    # Gemini Enterprise injects the OAuth connection as a state variable using the AUTH_ID key
    if hasattr(readonly_context, 'state') and readonly_context.state:
        for key, value in readonly_context.state.items():
            # Check for the dynamic FactSet Auth ID injected by Gemini Enterprise
            if "factset" in key.lower() or key.startswith("temp:"):
                user_token = value
                break
        
        # Fallback for Local testing script (checks mock session state)
        if not user_token:
            user_token = readonly_context.state.get('test_auth_token')

    # Failsafe: Strict enforcement.
    if not user_token:
        print("Security Warning: User token missing from context. Denying access.", flush=True)
        return {}

    print(f"🔒 SUCCESS: Intercepted OAuth Token! Starting with: {user_token[:15]}***", flush=True)

    return {
        "Authorization": f"Bearer {user_token}",
        "Content-Type": "application/json"
    }


# ---------------------------------------------------------------------------
# 2. DEPLOYMENT AUTH: One-time local token for schema fetching
# ---------------------------------------------------------------------------
def _get_initial_deployment_auth():
    """
    Fetches a single token locally so McpToolset can pull down 
    the tool schemas during initialization/deployment.
    """
    print("Fetching initial deployment auth...")
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    client = ConfidentialClient(config_path=config_path)
    token = client.get_access_token(    )
    print(f"Initial deployment auth: {token}")
    
    return token_to_scheme_credential(
        "oauth2Token", "header", "Authorization", token
    )

auth_scheme, auth_credential = _get_initial_deployment_auth()


# ---------------------------------------------------------------------------
# 3. SCHEMA PATCHES
# ---------------------------------------------------------------------------
def apply_patches():
    print("LOADING FLATENING + TYPING PATCH...")

    def flatten_schema_property(prop_name, prop_def):
        """
        Destructively simplifes a schema property to satisfy Vertex AI strictness.
        Removes anyOf/oneOf/allOf and enforces a single type.
        """
        if not isinstance(prop_def, dict):
            return

        # 1. Handle "anyOf", "oneOf", "allOf"
        complex_keys = ["anyOf", "oneOf", "allOf"]
        found_complex = next((k for k in complex_keys if k in prop_def), None)

        if found_complex:
            options = prop_def[found_complex]
            
            # Analyze options to pick the "Best" type
            is_array = False
            is_string = False
            
            if isinstance(options, list):
                for opt in options:
                    if isinstance(opt, dict):
                        t = opt.get("type")
                        if t == "array": is_array = True
                        if t == "string": is_string = True
            
            # REMOVE the complex block
            del prop_def[found_complex]

            # RE-INJECT a single simple type
            if is_array:
                prop_def["type"] = "array"
                # Ensure items exist
                if "items" not in prop_def:
                    prop_def["items"] = {"type": "string"}
            else:
                # Default to string for almost everything else (safest for LLMs)
                prop_def["type"] = "string"

        # 2. Handle missing types (fallback)
        if "type" not in prop_def:
            prop_def["type"] = "string"

        # 3. Handle 'null' types (Vertex rejects strict nulls)
        if prop_def.get("type") == "null":
             prop_def["type"] = "string"

        # 4. Recursion for Arrays
        if prop_def.get("type") == "array" and "items" in prop_def:
            flatten_schema_property(f"{prop_name}.items", prop_def["items"])
        
        # 5. Recursion for Objects
        if prop_def.get("type") == "object" and "properties" in prop_def:
            for k, v in prop_def["properties"].items():
                flatten_schema_property(f"{prop_name}.{k}", v)


    async def patched_get_tools(self, readonly_context: Optional[ReadonlyContext] = None) -> List[MCPTool]:
        headers = (self._header_provider(readonly_context) if self._header_provider and readonly_context else None)
        
        print(f"🌐 [MCP] Attempting connection to FactSet MCP Server: {self._connection_params.url} ...", flush=True)
        try:
            session = await self._mcp_session_manager.create_session(headers=headers)
            timeout = self._connection_params.timeout if hasattr(self._connection_params, "timeout") else None
            tools_response = await asyncio.wait_for(session.list_tools(), timeout=timeout)
            print(f"✅ [MCP] Successfully pulled {len(tools_response.tools) if tools_response else 0} tools from FactSet!", flush=True)
        except Exception as e:
            print(f"⚠️ Graceful degradation: Failed to initialize MCP connection or fetch tools: {e}", flush=True)
            return [] # Return empty tool list to prevent 500 error stream crashes

        final_tool_list = []
        
        if tools_response and hasattr(tools_response, 'tools'):
            for raw_tool in tools_response.tools:
                try:
                    # Extract Dict
                    current_schema = getattr(raw_tool, "inputSchema", {})
                    if hasattr(current_schema, "model_dump"): schema_dict = current_schema.model_dump()
                    elif hasattr(current_schema, "dict"): schema_dict = current_schema.dict()
                    else: schema_dict = current_schema

                    if isinstance(schema_dict, dict):
                        new_schema = copy.deepcopy(schema_dict)
                        properties = new_schema.get("properties", {})
                        
                        # Apply Flattening to every property
                        for k, v in properties.items():
                            flatten_schema_property(k, v)
                        
                        # Force Update
                        try:
                            raw_tool.inputSchema = new_schema
                        except Exception:
                            raw_tool.__dict__["inputSchema"] = new_schema
                except Exception as e:
                    print(f"Patch Error on {raw_tool.name}: {e}")

                mcp_tool = MCPTool(
                    mcp_tool=raw_tool,
                    mcp_session_manager=self._mcp_session_manager,
                    auth_scheme=self._auth_scheme,
                    auth_credential=self._auth_credential,
                    require_confirmation=self._require_confirmation,
                    header_provider=self._header_provider,
                )
                if self._is_tool_selected(mcp_tool, readonly_context):
                    final_tool_list.append(mcp_tool)

        return final_tool_list

    McpToolset.get_tools = retry_on_errors(patched_get_tools)

    # Patch McpToolset to be deepcopy-safe.
    # McpToolset stores sys.stderr (_io.TextIOWrapper) in _errlog and
    # MCPSessionManager, plus asyncio.Lock objects — none of which can be
    # deepcopied/pickled. We reconstruct a fresh instance instead.
    def mcptoolset_deepcopy(self, memo):
        return McpToolset(
            connection_params=copy.deepcopy(self._connection_params, memo),
            auth_scheme=copy.deepcopy(self._auth_scheme, memo),
            auth_credential=copy.deepcopy(self._auth_credential, memo),
            require_confirmation=self._require_confirmation,
            header_provider=copy.deepcopy(self._header_provider, memo),
        )
    McpToolset.__deepcopy__ = mcptoolset_deepcopy

    print("McpToolset patched with flattening + deepcopy support.")

apply_patches()

# ---------------------------------------------------------------------------
# 4. CUSTOM AGENT TOOLS
# ---------------------------------------------------------------------------
def calculate_growth_rate(current_value: float, previous_value: float) -> float:
    """
    Calculates the percentage growth rate between two financial periods.
    Use this when FactSet returns raw revenue/earnings data but you need the % growth.
    """
    if previous_value == 0: return 0.0
    return ((current_value - previous_value) / previous_value) * 100.0

def get_simulated_stock_history(ticker: str) -> list[dict]:
    """
    Get historical prices for a ticker natively when FactSet MCP tools are unavailable for prices.
    Returns simulated standard JSON pricing data.
    """
    import random
    base = 150 + len(ticker) * 2
    return [{"date": f"2026-03-{i:02d}", "price": round(base + random.uniform(-5.0, 5.0), 2)} for i in range(1, 10)]

def get_current_datetime() -> str:
    """
    Returns the current date and time. Always call this FIRST when answering a query asking for 'today', 
    'yesterday', 'last year', or 'year-to-date' to calculate strict startDate and endDate values for FactSet tools.
    """
    from datetime import datetime
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

# ---------------------------------------------------------------------------
# 5. AGENT CONFIGURATION
# ---------------------------------------------------------------------------
root_agent = LlmAgent(
    model="gemini-2.5-pro",
    name='Assistant',
    instruction="""You are an elite Quantitative Financial Analyst for FactSet Inc., armed with advanced MCP integrations.
Your primary goal is to answer complex stakeholder financial queries by combining data from your various tools.

GENERAL INSTRUCTIONS:
1. **Real-Time Date**: Always use `get_current_datetime` FIRST to establish the current timezone and date for `startDate` and `endDate` params. DO NOT hallucinate dates.
2. If FactSet_Fundamentals returns empty, IMMEDIATELY try FactSet_EstimatesConsensus which often has the latest actuals.
3. If a tool is missing or returns an error, use your internal knowledge or admit you cannot answer. DO NOT hallucinate tool calls or fake ticker data.

CRITICAL TOOL PARAMETER RULES (MUST FOLLOW):
When calling FactSet tools, you MUST use these EXACT parameter values to avoid API crashes:
- **Parameter Naming**: Always use `ids` (not `tickers`). Always use `startDate` / `endDate` in camelCase (never snake_case).

### FactSet_Fundamentals
- data_type: MUST be exactly "fundamentals"
- metrics: Use FF_ prefix (FF_SALES, FF_EPS_BASIC, FF_NET_MGN, FF_DEBT, FF_ROE)

### FactSet_GlobalPrices
- data_type: MUST be one of: "prices", "returns", "corporate_actions", "annualized_dividends", "shares_outstanding"
- frequency: Use `AQ` for Quarterly, `AY` for Yearly (Never FQ/FY)

### FactSet_Ownership
- data_type: MUST be one of: "fund_holdings", "security_holders", "insider_transactions", "institutional_transactions"

### FactSet_EstimatesConsensus
- estimate_type: MUST be one of: "consensus_fixed", "consensus_rolling", "surprise", "ratings", "segments", "guidance"
- metrics: NO FF_ prefix (use SALES, EPS, EBITDA, PRICE_TGT)

### FactSet_People
- data_type: MUST be one of: "profiles", "jobs", "company_people", "company_positions", "company_compensation", "company_stats"

### FactSet_SupplyChain
- relationshipType: MUST be one of: "COMPETITORS", "CUSTOMERS", "SUPPLIERS", "PARTNERS"
""",
    tools=[
        McpToolset(
            connection_params=StreamableHTTPServerParams(
                url='https://mcp.factset.com/content/v1/',
            ),
            auth_scheme=auth_scheme,
            auth_credential=auth_credential,
            # Pass the function reference directly
            header_provider=get_factset_headers 
        ),
        calculate_growth_rate,
        get_simulated_stock_history,
        get_current_datetime
    ]
)