import httpx
from fastmcp import FastMCP
import json

# Create an HTTP client for your API
client = httpx.AsyncClient(base_url="http://127.0.0.1:8000")

# Load your OpenAPI spec
with open("openapi_contract.json", "r") as file:
	openapi_spec = json.load(file)

# Create the MCP server
mcp = FastMCP.from_openapi(
    openapi_spec=openapi_spec,
    client=client,
    name="My API Server"
)

if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=9000)

