import httpx


class OllamaUnavailable(Exception):
    pass


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: float = 90, client: httpx.Client | None = None):
        self.base_url, self.model = base_url.rstrip("/"), model
        self.client = client or httpx.Client(timeout=timeout)

    def status(self) -> dict:
        try:
            r = self.client.get(f"{self.base_url}/api/tags", timeout=3)
            r.raise_for_status()
            models = [m["name"] for m in r.json().get("models", [])]
        except (httpx.HTTPError, ValueError) as e:
            return {"reachable": False, "model": self.model, "model_available": False, "error": type(e).__name__}
        return {
            "reachable": True,
            "model": self.model,
            "model_available": self.model in models,
            "installed_models": models,
        }

    def chat(self, system: str, user: str) -> str:
        try:
            r = self.client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "think": False,
                    "options": {"temperature": 0.1},
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                },
            )
            r.raise_for_status()
            return r.json()["message"]["content"].strip()
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise OllamaUnavailable(type(e).__name__) from None
