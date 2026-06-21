"""
mcp_server/server.py — TelecomAI MCP Server (fictional demo)
================================================================
Slack Agent Builder Challenge — required technology: MCP server
integration.

This MCP server exposes the TelecomAI diagnostic engine as tools
that Slack (via its native "MCP Servers" connector) or any other
MCP-compatible client can call directly.

All data in this project is entirely fictional, created for this
hackathon demo only.

Tools exposed:
  - check_subscriber_status(numero)
  - get_connection_history(numero, months)

Run locally:
  python mcp_server/server.py

This starts a Streamable HTTP MCP server on http://0.0.0.0:8000/mcp
which can then be exposed publicly (e.g. via ngrok) for Slack to
connect to.
"""

import os, sys, re
from datetime import date

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.agent import TelecomAIAgent
from core.aaa_mock import AAAMockClient

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("TelecomAI Agent", host="0.0.0.0", port=8000)

MOIS_NOMS = {
    1:"January",2:"February",3:"March",4:"April",5:"May",6:"June",
    7:"July",8:"August",9:"September",10:"October",11:"November",12:"December"
}
MOIS_EN = {v.lower(): k for k, v in MOIS_NOMS.items()}


@mcp.tool()
def check_subscriber_status(numero: str) -> dict:
    """
    Check the current AAA status and diagnosis for a fiber (FTTH)
    subscriber line.

    Args:
        numero: The 9-digit subscriber number (e.g. "222230906")

    Returns:
        A dictionary with the subscriber's zone, AAA status,
        diagnosis category, a human-readable message, the
        recommended action, and an urgency level.
    """
    numero = re.sub(r"[^\d]", "", str(numero))
    if len(numero) != 9:
        return {"error": "Invalid subscriber number. It must be exactly 9 digits."}

    agent = TelecomAIAgent()
    res = agent.traiter(numero)

    return {
        "numero":           numero,
        "zone":             res.get("zone", {}).get("zone", "Unknown"),
        "aaa_status":       res.get("statut", "?"),
        "category":         res.get("categorie", "INCONNU"),
        "diagnosis":        res.get("reponse_whatsapp", ""),
        "recommended_action": res.get("action_required", "info_only"),
        "urgency":          res.get("urgence", "NORMAL"),
    }


@mcp.tool()
def get_connection_history(numero: str, months: list[str] = None) -> dict:
    """
    Get the connection (authentication) history for a fiber (FTTH)
    subscriber line, for one or more months.

    Args:
        numero: The 9-digit subscriber number (e.g. "222302628")
        months: Optional list of months to check, formatted as
                "May 2026", "June 2026", etc. If not provided,
                defaults to the current month.

    Returns:
        A dictionary with the subscriber's zone and, for each
        requested month, the first and last authentication
        timestamps (or a note if no authentication was recorded).
    """
    numero = re.sub(r"[^\d]", "", str(numero))
    if len(numero) != 9:
        return {"error": "Invalid subscriber number. It must be exactly 9 digits."}

    agent = TelecomAIAgent()
    res   = agent.traiter(numero)
    zone  = res.get("zone", {})

    mois_liste = []
    if months:
        for m in months:
            ml = m.lower()
            for nom, num in MOIS_EN.items():
                if nom in ml:
                    annees = re.findall(r'20\d{2}', m)
                    annee = int(annees[0]) if annees else date.today().year
                    if (annee, num) not in mois_liste:
                        mois_liste.append((annee, num))
    if not mois_liste:
        auj = date.today()
        mois_liste = [(auj.year, auj.month)]

    aaa = AAAMockClient()
    history = {}
    for (annee, mois) in mois_liste:
        cdr = aaa.consulter_cdr(numero, mois, annee)
        cle = f"{MOIS_NOMS[mois]} {annee}"
        if cdr["total"] == 0:
            history[cle] = "No authentication on record"
        else:
            history[cle] = {
                "first_authentication": cdr["premiere"],
                "last_authentication":  cdr["derniere"],
            }

    return {
        "numero":  numero,
        "zone":    zone.get("zone", "Unknown"),
        "history": history,
    }


if __name__ == "__main__":
    print("\n" + "="*60)
    print("  TELECOMAI AGENT — MCP Server")
    print("  Slack Agent Builder Challenge")
    print("="*60)
    print("\nExposing tools: check_subscriber_status, get_connection_history")
    print("Listening on http://0.0.0.0:8000/mcp")
    print("Press Ctrl+C to stop\n")
    mcp.run(transport="streamable-http")
