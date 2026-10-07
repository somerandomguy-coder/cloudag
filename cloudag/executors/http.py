import re
from typing import Any, Callable, Dict, Optional
import httpx
from cloudag.executors.base import BaseExecutor, ExecutionContext
from cloudag.models.schema import StepDefinition


class HTTPExecutor(BaseExecutor):
    """Async HTTP/Webhook/Lambda executor using httpx."""

    def __init__(
        self,
        client: Optional[httpx.AsyncClient] = None,
        mock_handler: Optional[Callable[[httpx.Request], httpx.Response]] = None,
    ):
        self._custom_client = client
        self._mock_handler = mock_handler

    def _parse_action(self, action: str) -> tuple[str, str]:
        """Extracts HTTP method and URL from action string (e.g. 'POST https://api.io/run')."""
        match = re.match(r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(https?://\S+)$", action.strip(), re.IGNORECASE)
        if match:
            return match.group(1).upper(), match.group(2)
        if action.startswith("http://") or action.startswith("https://"):
            return "GET", action.strip()
        return "GET", action.strip()

    async def execute(
        self,
        step: StepDefinition,
        resolved_inputs: Dict[str, Any],
        context: ExecutionContext,
    ) -> Any:
        default_method, default_url = self._parse_action(step.action)
        method = resolved_inputs.get("method", default_method).upper()
        url = resolved_inputs.get("url", default_url)

        headers = resolved_inputs.get("headers", {})
        params = resolved_inputs.get("params", None)
        timeout_sec = float(resolved_inputs.get("timeout", step.timeout_seconds))

        # Determine payload
        json_body = None
        data_body = None

        if "json" in resolved_inputs:
            json_body = resolved_inputs["json"]
        elif "data" in resolved_inputs:
            data_body = resolved_inputs["data"]
        elif method in ("POST", "PUT", "PATCH"):
            # Exclude control keys and treat remaining inputs as json body
            reserved_keys = {"method", "url", "headers", "params", "timeout"}
            payload = {k: v for k, v in resolved_inputs.items() if k not in reserved_keys}
            if payload:
                json_body = payload
        elif method == "GET" and params is None:
            # If GET and params not explicitly set, remaining inputs can serve as params
            reserved_keys = {"method", "url", "headers", "params", "timeout"}
            query_params = {k: v for k, v in resolved_inputs.items() if k not in reserved_keys}
            if query_params:
                params = query_params

        # Build client
        if self._custom_client:
            client = self._custom_client
            owns_client = False
        elif self._mock_handler:
            transport = httpx.MockTransport(self._mock_handler)
            client = httpx.AsyncClient(transport=transport, timeout=timeout_sec)
            owns_client = True
        else:
            client = httpx.AsyncClient(timeout=timeout_sec)
            owns_client = True

        try:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json_body,
                data=data_body,
            )
            response.raise_for_status()

            # Attempt to parse json
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type or response.text.startswith(("{", "[")):
                try:
                    return response.json()
                except Exception:
                    pass

            return {
                "status_code": response.status_code,
                "text": response.text,
                "headers": dict(response.headers),
            }
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"HTTP request to '{url}' failed with status {e.response.status_code}: {e.response.text}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"HTTP request to '{url}' failed: {str(e)}") from e
        finally:
            if owns_client:
                await client.aclose()
