from mcp.server.mcpserver import MCPServer
import tools

mcp = MCPServer("haze-agent")


@mcp.tool()
def get_psi(region: str) -> dict:
    """Get the current 24-hr PSI and level for a Singapore region
    (north/south/east/west/central) or area (e.g. bedok, jurong)."""
    return tools.get_psi(region)


@mcp.tool()
def search_advisories(question: str, psi: int) -> list:
    """Search official NEA and MOM haze guidelines for advice relevant
    to the question at the given PSI. Call get_psi first to get the PSI."""
    return tools.search_advisories(question, psi)


if __name__ == "__main__":
    mcp.run()