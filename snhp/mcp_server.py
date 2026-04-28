import sys
import json
import logging
import traceback
import os
from dotenv import load_dotenv

logging.basicConfig(level=logging.DEBUG, filename='/tmp/snhp_mcp.log', filemode='a',
                    format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv(os.path.join(os.path.dirname(__file__), '../.env'))

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# SNHP Core imports
import snhp

# ──────── JSON-RPC Boilerplate ────────
def send_response(response_dict):
    res_str = json.dumps(response_dict)
    sys.stdout.write(res_str + "\n")
    sys.stdout.flush()
    logging.debug(f"Sent: {res_str}")

def handle_initialize(msg_id):
    send_response({
        "jsonrpc": "2.0", "id": msg_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "snhp-shadow-negotiator", "version": "3.1.0"},
        },
    })

def handle_tools_list(msg_id):
    send_response({
        "jsonrpc": "2.0", "id": msg_id,
        "result": {
            "tools": [{
                "name": "snhp_evaluate_negotiation",
                "description": "Calculates the mathematically optimal counter-offer for a contract. Only requires the client email and your raw natural language constraints.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "client_email": {
                            "type": "string",
                            "description": "The exact raw text of the email or message sent by the client.",
                        },
                        "freelancer_constraints": {
                            "type": "string",
                            "description": "Your constraints and demands in natural English (e.g. 'I want 100/hr, max 4 hours per day for 2 weeks, absolute minimum total is 3000').",
                        },
                        "tone": {
                            "type": "string",
                            "description": "Optional tone for the drafted reply: 'professional' (default), 'friendly', or 'firm'.",
                            "enum": ["professional", "friendly", "firm"],
                        },
                        "negotiation_context": {
                            "type": "string",
                            "description": "Optional context from previous negotiation rounds (e.g. 'This is round 2, they rejected my $5000 offer').",
                        },
                    },
                    "required": ["client_email", "freelancer_constraints"],
                },
            }],
        },
    })

# ──────── MCP Handler ────────
def handle_tools_call(msg_id, params):
    name = params.get("name")
    args = params.get("arguments", {})

    if name == "snhp_evaluate_negotiation":
        try:
            if any(k not in ["client_email", "freelancer_constraints"] for k in args.keys()):
                raise ValueError("Zero-Tuning Abstraction Enforced: Mathematical parameters are derived strictly from language. Direct numerical tuning is forbidden.")
                
            client_email = args.get("client_email")
            constraints = args.get("freelancer_constraints")
            tone = args.get("tone", "professional")
            context = args.get("negotiation_context")
            
            # SNHP Core SDK Invocation
            response = snhp.negotiate(client_email, constraints, tone=tone, negotiation_context=context)
            output = snhp.format_markdown(response)

            send_response({
                "jsonrpc": "2.0", "id": msg_id,
                "result": {"content": [{"type": "text", "text": output}]},
            })
        except Exception as e:
            logging.error(f"SNHP error: {traceback.format_exc()}")
            send_response({
                "jsonrpc": "2.0", "id": msg_id,
                "error": {"code": -32603, "message": f"Internal error: {str(e)}"},
            })
    else:
        send_response({
            "jsonrpc": "2.0", "id": msg_id,
            "error": {"code": -32601, "message": "Tool not found"},
        })

def main():
    logging.info("SNHP MCP Server v3.1 SDK Wrapper starting...")
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
            if msg.get("jsonrpc") != "2.0":
                continue
            method = msg.get("method")
            msg_id = msg.get("id")
            if method == "initialize":
                handle_initialize(msg_id)
            elif method == "tools/list":
                handle_tools_list(msg_id)
            elif method == "tools/call":
                handle_tools_call(msg_id, msg.get("params"))
            elif msg_id:
                send_response({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "Method not found"}})
        except json.JSONDecodeError:
            pass
        except Exception as e:
            if "msg" in locals() and msg.get("id"):
                send_response({"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32603, "message": "Routing error: " + str(e)}})

if __name__ == "__main__":
    main()
