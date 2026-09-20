import json
from urllib.request import Request, urlopen


class OdooClient:
    """Minimal JSON-RPC client. Credentials stay in environment variables."""
    def __init__(self, url: str, database: str, username: str, password: str):
        self.url, self.database, self.username, self.password = url.rstrip("/"), database, username, password

    def call(self, service: str, method: str, *args):
        payload = json.dumps({"jsonrpc": "2.0", "method": "call", "params": {"service": service, "method": method, "args": args}, "id": 1}).encode()
        request = Request(f"{self.url}/jsonrpc", data=payload, headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=20) as response:
            result = json.load(response)
        if result.get("error"): raise RuntimeError(result["error"])
        return result["result"]

    def authenticate(self) -> int:
        return self.call("common", "authenticate", self.database, self.username, self.password, {})
