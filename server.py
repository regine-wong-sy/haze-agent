from mcp.server.mcpserver import MCPServer
import tools
import agent
import router

mcp = MCPServer("haze-agent")


@mcp.tool()
def get_psi(region: str) -> dict:
    """Get the current 24-hr PSI and level for a Singapore region
    (north/south/east/west/central) or area (e.g. bedok, jurong)."""
    return tools.get_psi(region)


@mcp.tool()
def ask_haze_agent(question: str) -> dict:
    """Answer a Singapore haze safety question end to end, using live PSI and
    official NEA/MOM guidelines. Questions with personal health information are
    answered by a local model so that data never leaves this machine."""
    route, reason = router.pick_route(question)
    answer = agent.ask(question, route=route)
    return {"model_used": route, "reason": reason, "answer": answer}

@mcp.tool()
def search_advisories(question: str, psi: int) -> list:
    """Search official NEA and MOM haze guidelines for advice relevant
    to the question at the given PSI. Call get_psi first to get the PSI."""
    return tools.search_advisories(question, psi)


if __name__ == "__main__":
    mcp.run()