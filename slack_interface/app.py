"""
slack_interface/app.py — Slack interface (fictional demo)
============================================================
TelecomAI Agent — Slack slash command interface
Slack Agent Builder Challenge — Slack Agent for Organizations

This file is part of a hackathon demo project. All company names
and contact details are entirely fictional.

Usage in Slack:
  /ftth <message describing the request>

Examples:
  /ftth Please check the status of line 222230906
  /ftth subscriber 222316544 has a password issue
  /ftth last authentication dates for May and June 2026 - line 222302628
"""

import os, sys, re, json
from datetime import date
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from openai import OpenAI
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.agent import TelecomAIAgent
from core.aaa_mock import AAAMockClient

load_dotenv()

# ── Qwen client (same engine as the email interface) ───────────
qwen = OpenAI(
    api_key=os.getenv("QWEN_API_KEY"),
    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
)
MODEL = "qwen-plus"

# ── Slack app (Socket Mode — no public server needed) ──────────
app = App(token=os.getenv("SLACK_BOT_TOKEN"))

MOIS_NOMS = {
    1:"January",2:"February",3:"March",4:"April",5:"May",6:"June",
    7:"July",8:"August",9:"September",10:"October",11:"November",12:"December"
}
MOIS_EN = {
    "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
    "july":7,"august":8,"september":9,"october":10,"november":11,"december":12
}


def analyser_message(texte: str) -> dict:
    """Use Qwen to extract the subscriber number, request type, and months."""
    prompt = f"""You analyze internal support requests sent in a fictional
ISP's Slack workspace, about fiber (FTTH) subscriber lines.

MESSAGE: {texte}

Classify the request type:
- STATUS: the message reports ANY problem (no internet, password
  issue, connection problem, suspended account, slow speed, etc.),
  asks to check the CURRENT status of a line, OR is simply a bare
  subscriber number with no other context.
- CDR: the message EXPLICITLY asks for connection HISTORY, PAST
  DATES of authentication, or "when did this happen" — not a
  general problem report.
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
            messages=[{"role":"user","content":prompt}]
        )
        txt = r.choices[0].message.content.strip()
        txt = txt.replace("```json","").replace("```","").strip()
        data = json.loads(txt)
        num_brut = data.get("numero")
        resultat = {
            "numero": str(num_brut) if num_brut is not None else None,
            "type":   data.get("type","STATUS"),
            "mois":   data.get("mois")
        }
    except Exception as e:
        print(f"[DEBUG] Qwen extraction failed: {e}")

    # Safety net: always try a direct regex match if Qwen found nothing
    if not resultat.get("numero"):
        m = re.search(r'\b\d{9}\b', texte)
        if m:
            resultat["numero"] = m.group()
            if resultat.get("type") in (None, "UNKNOWN"):
                resultat["type"] = "STATUS"

    return resultat

def convertir_mois(mois_texte):
    """Convert ['May 2026','June 2026'] -> [(2026,5),(2026,6)]"""
    if not mois_texte:
        return None
    res = []
    for m in mois_texte:
        ml = m.lower()
        for nom, num in MOIS_EN.items():
            if nom in ml:
                annees = re.findall(r'20\d{2}', m)
                annee = int(annees[0]) if annees else date.today().year
                if (annee, num) not in res:
                    res.append((annee, num))
    return res or None


def formater_reponse_slack(numero: str, resultat: dict) -> str:
    """Format the diagnosis as a Slack message (mrkdwn)."""
    cat        = resultat.get("categorie", "INCONNU")
    zone       = resultat.get("zone", {})
    statut     = resultat.get("statut", "?")
    recommande = resultat.get("reponse_whatsapp", "")
    urgence    = resultat.get("urgence", "NORMAL")

    emoji = {
        "NORMAL": ":white_check_mark:", "NORMAL_SANS_TRAFIC": ":warning:",
        "ABSENCE_AUTH": ":wrench:", "MOT_DE_PASSE": ":key:",
        "ECHEC_AUTH": ":wrench:", "BLOCAGE_CRM": ":clipboard:",
        "SUSPENDU": ":red_circle:", "INEXISTANT": ":grey_question:",
        "INCONNU": ":grey_question:",
    }.get(cat, ":satellite:")

    lines = [
        f"{emoji} *Line {numero}* — {zone.get('zone','Unknown zone')}",
        f"*AAA status:* {statut}",
        f"*Diagnosis:* {recommande}",
    ]
    if urgence == "HIGH":
        lines.append(":rotating_light: *Urgency: HIGH* — human review required "
                      "before resetting the password.")
    return "\n".join(lines)


def formater_cdr_slack(numero: str, zone: dict, mois_liste) -> str:
    """Format a connection-history (CDR) response for Slack."""
    aaa = AAAMockClient()
    if not mois_liste:
        auj = date.today()
        mois_liste = [(auj.year, auj.month)]

    lines = [f":calendar: *Connection history — {numero}* "
             f"({zone.get('zone','Unknown zone')})"]
    for (annee, mois) in mois_liste:
        cdr = aaa.consulter_cdr(numero, mois, annee)
        nom = f"{MOIS_NOMS[mois]} {annee}"
        if cdr["total"] == 0:
            lines.append(f"• {nom}: no authentication on record")
        else:
            p = cdr["premiere"].replace(" "," at ",1) if cdr["premiere"] else "N/A"
            d = cdr["derniere"].replace(" "," at ",1) if cdr["derniere"] else "N/A"
            lines.append(f"• {nom}: first auth on {p}, last auth on {d}")
    return "\n".join(lines)


@app.command("/ftth")
def handle_ftth_command(ack, respond, command):
    """Handle the /ftth slash command."""
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

    agent = TelecomAIAgent()
    res   = agent.traiter(numero)

    if type_req == "CDR":
        mois_liste = convertir_mois(mois) if mois else None
        message = formater_cdr_slack(numero, res.get("zone", {}), mois_liste)
    else:
        message = formater_reponse_slack(numero, res)

    respond(message)


if __name__ == "__main__":
    handler = SocketModeHandler(app, os.getenv("SLACK_APP_TOKEN"))
    print("\n" + "="*60)
    print("  TELECOMAI AGENT — Slack interface (Socket Mode)")
    print("  Slack Agent Builder Challenge")
    print("="*60)
    print("\nListening for /ftth commands in your Slack workspace...")
    print("Press Ctrl+C to stop\n")
    handler.start()
