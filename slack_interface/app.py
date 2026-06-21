"""
slack_interface/app.py — Slack interface (fictional demo) — v2
==================================================================
TelecomAI Agent — Slack slash command interface
Slack Agent Builder Challenge — required technology: MCP server
integration.

This app acts as a real MCP CLIENT: the /ftth command connects to
our own TelecomAI MCP server (mcp_server/server.py) via the actual
Model Context Protocol, instead of calling the diagnostic engine
directly. This demonstrates genuine MCP server integration as a
core architectural piece of the project.

All company names and contact details are entirely fictional.

Usage in Slack:
  /ftth <message describing the request>
"""

import os, sys, re, json, asyncio
from openai import OpenAI
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

load_dotenv()

# ── Qwen client (natural language understanding) ────────────────
qwen = OpenAI(
    api_key=os.getenv("QWEN_API_KEY"),
    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
)
MODEL = "qwen-plus"

# ── Our own MCP server (started separately via mcp_server/server.py) ──
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp")

# ── Slack app (Socket Mode) ──────────────────────────────────────
app = App(token=os.getenv("SLACK_BOT_TOKEN"))


def analyser_message(texte: str) -> dict:
    """Use Qwen to extract the subscriber number, request type, and months."""
    prompt = f"""You analyze internal support requests sent in a fictional
ISP's Slack workspace, about fiber (FTTH) subscriber lines.

MESSAGE: {texte}

Classify the request type:
- STATUS: the message reports ANY problem, asks to check the
  CURRENT status of a line, or is simply a bare subscriber number.
- CDR: the message EXPLICITLY asks for connection HISTORY or PAST
  DATES of authentication.
- UNKNOWN: neither of the above.

When in doubt, choose STATUS.

Respond ONLY with valid JSON:
{{
  "numero": "the 9-digit subscriber number or null",
  "type": "STATUS or CDR or UNKNOWN",
  "mois": ["May 2026", "June 2026"] if specific months are mentioned, else null
}}
Respond ONLY with the JSON, no explanation."""

    resultat = {"numero": None, "type": "STATUS", "mois": None}
    try:
        r = qwen.chat.completions.create(
            model=MODEL, max_tokens=100,
            messages=[{"role": "user", "content": prompt}]
        )
        txt = r.choices[0].message.content.strip()
        txt = txt.replace("```json", "").replace("```", "").strip()
        data = json.loads(txt)
        num_brut = data.get("numero")
        resultat = {
            "numero": str(num_brut) if num_brut is not None else None,
            "type":   data.get("type", "STATUS"),
            "mois":   data.get("mois")
        }
    except Exception as e:
        print(f"[DEBUG] Qwen extraction failed: {e}")

    if not resultat.get("numero"):
        m = re.search(r'\b\d{9}\b', texte)
        if m:
            resultat["numero"] = m.group()
            if resultat.get("type") in (None, "UNKNOWN"):
                resultat["type"] = "STATUS"

    return resultat


async def call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    """Call a tool on our TelecomAI MCP server via the real MCP protocol."""
    async with streamablehttp_client(MCP_SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            text = result.content[0].text
            return json.loads(text)


def formater_reponse_slack(data: dict) -> str:
    """Format an MCP check_subscriber_status result as a Slack message."""
    if "error" in data:
        return f":warning: {data['error']}"

    cat = data.get("category", "INCONNU")
    emoji = {
        "NORMAL": ":white_check_mark:", "NORMAL_SANS_TRAFIC": ":warning:",
        "ABSENCE_AUTH": ":wrench:", "MOT_DE_PASSE": ":key:",
        "ECHEC_AUTH": ":wrench:", "BLOCAGE_CRM": ":clipboard:",
        "SUSPENDU": ":red_circle:", "INEXISTANT": ":grey_question:",
        "INCONNU": ":grey_question:",
    }.get(cat, ":satellite:")

    lines = [
        f"{emoji} *Line {data.get('numero')}* — {data.get('zone', 'Unknown zone')}",
        f"*AAA status:* {data.get('aaa_status', '?')}",
        f"*Diagnosis:* {data.get('diagnosis', '')}",
    ]
    if data.get("urgency") == "HIGH":
        lines.append(":rotating_light: *Urgency: HIGH* — human review required "
                      "before resetting the password.")
    return "\n".join(lines)


def formater_cdr_slack(data: dict) -> str:
    """Format an MCP get_connection_history result as a Slack message."""
    if "error" in data:
        return f":warning: {data['error']}"

    lines = [f":calendar: *Connection history — {data.get('numero')}* "
             f"({data.get('zone', 'Unknown zone')})"]
    for mois, info in data.get("history", {}).items():
        if isinstance(info, str):
            lines.append(f"• {mois}: {info}")
        else:
            lines.append(f"• {mois}: first auth on {info.get('first_authentication')}, "
                          f"last auth on {info.get('last_authentication')}")
    return "\n".join(lines)


@app.command("/ftth")
def handle_ftth_command(ack, respond, command):
    """Handle the /ftth slash command by calling our MCP server."""
    ack()
    texte = command.get("text", "").strip()

    if not texte:
        respond("Please provide a subscriber number or describe the issue.\n"
                 "Example: `/ftth subscriber 222316544 has a password issue`")
        return

    analyse  = analyser_message(texte)
    numero   = analyse.get("numero")
    type_req = analyse.get("type", "STATUS")
    mois     = analyse.get("mois")

    if not numero:
        respond(":grey_question: I couldn't find a 9-digit subscriber number "
                 "in your request. Please include one.")
        return

    try:
        if type_req == "CDR":
            data = asyncio.run(call_mcp_tool(
                "get_connection_history", {"numero": numero, "months": mois}
            ))
            message = formater_cdr_slack(data)
        else:
            data = asyncio.run(call_mcp_tool(
                "check_subscriber_status", {"numero": numero}
            ))
            message = formater_reponse_slack(data)
    except Exception as e:
        message = f":x: Could not reach the TelecomAI MCP server: {e}"

    respond(message)


if __name__ == "__main__":
    handler = SocketModeHandler(app, os.getenv("SLACK_APP_TOKEN"))
    print("\n" + "="*60)
    print("  TELECOMAI AGENT — Slack interface (MCP client)")
    print("  Slack Agent Builder Challenge")
    print("="*60)
    print(f"\nConnecting to MCP server at: {MCP_SERVER_URL}")
    print("Listening for /ftth commands in your Slack workspace...")
    print("Press Ctrl+C to stop\n")
    handler.start()
