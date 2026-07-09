"""A 25-line community bot: greedy opener, concede lowest-weight issues over time,
accept when the offer clears a time-decaying bar. The submit.html starter kit."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class Bot(BaseHTTPRequestHandler):
    def do_POST(self):
        m = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        t = (m["turn"] + 1) / m["deadline"]
        names = [i["name"] for i in m["issues"]]
        if m["their_offers"]:
            u = sum(m["weights"][i["name"]] * i["my_utility"][i["options"].index(m["their_offers"][-1][i["name"]])]
                    for i in m["issues"])
            if u >= max(m["batna"], 0.62 - 0.35 * t):
                return self._send({"action": "accept"})
        by_weight = sorted(names, key=lambda n: m["weights"][n])
        concede = set(by_weight[:int(t * (len(names) - 1))])
        pkg = {}
        for i in m["issues"]:
            j = len(i["options"]) // 2 if i["name"] in concede else max(
                range(len(i["options"])), key=lambda k: i["my_utility"][k])
            pkg[i["name"]] = i["options"][j]
        self._send({"action": "offer", "package": pkg})
    def _send(self, obj):
        d = json.dumps(obj).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(d))); self.end_headers()
        self.wfile.write(d)
    def log_message(self, *a): pass

ThreadingHTTPServer(("127.0.0.1", 8377), Bot).serve_forever()
