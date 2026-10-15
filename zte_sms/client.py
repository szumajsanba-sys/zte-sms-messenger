from __future__ import annotations

import logging
import time
from typing import Any

import requests

from .auth import AuthResult, ZteAuth
from .models import AppSettings

LOGGER = logging.getLogger(__name__)


class ZteClient:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.base_url = settings.router_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "ZTE SMS Keeper/1.0",
                "Referer": f"{self.base_url}/index.html#sms",
                "Accept": "application/json, text/plain, */*",
                "X-Requested-With": "XMLHttpRequest",
            }
        )
        self.auth = ZteAuth(self.session, self.base_url, settings.password, settings.request_timeout)

    def check_router(self) -> bool:
        try:
            response = self.session.get(f"{self.base_url}/index.html#sms", timeout=10)
            return response.ok
        except requests.RequestException:
            return False

    def ensure_authenticated(self) -> AuthResult:
        return self.auth.ensure_authenticated()

    def fetch_sms_raw(self, mem_store: int | None = None, data_per_page: int | None = None) -> str:
        mem_store = mem_store if mem_store is not None else self.settings.mem_store
        data_per_page = data_per_page if data_per_page is not None else self.settings.data_per_page
        url = f"{self.base_url}/goform/goform_get_cmd_process"
        params: dict[str, Any] = {
            "isTest": "false",
            "cmd": "sms_data_total",
            "page": "0",
            "data_per_page": str(data_per_page),
            "mem_store": str(mem_store),
            "tags": "10",
            "order_by": "order by id desc",
            "_": str(int(time.time() * 1000)),
        }
        last_error: Exception | None = None
        for attempt in range(self.settings.retry_count + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.settings.request_timeout)
                response.raise_for_status()
                return response.text
            except requests.RequestException as exc:
                last_error = exc
                LOGGER.warning("Fetch SMS failed, attempt %s: %s", attempt + 1, exc)
                time.sleep(min(2 + attempt, 5))
        raise RuntimeError(f"Не удалось получить SMS: {last_error}")

    def post_goform(self, body: dict[str, Any], add_accessible_id: bool = True) -> requests.Response:
        data = dict(body)
        if add_accessible_id and data.get("goformId") not in {"LOGIN", "SET_WEB_LANGUAGE"}:
            data["AD"] = self.auth.make_accessible_id()
        url = f"{self.base_url}/goform/goform_set_cmd_process"
        return self.session.post(url, data=data, timeout=self.settings.request_timeout)

    def get_cmd(self, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/goform/goform_get_cmd_process"
        request_params = {"isTest": "false", **params, "_": str(int(time.time() * 1000))}
        response = self.session.get(url, params=request_params, timeout=self.settings.request_timeout)
        response.raise_for_status()
        return response.json()

    def delete_sms(self, ids: list[str], dry_run: bool = True) -> tuple[bool, str]:
        if not ids:
            return True, "Нет SMS для удаления."
        if dry_run:
            return True, f"Dry-run: роутеру был бы отправлен список {len(ids)} SMS."

        body = {
            "isTest": "false",
            "goformId": "DELETE_SMS",
            "msg_id": ";".join(ids) + ";",
            "notCallback": "true",
        }
        response = self.post_goform(body)
        text = response.text.strip()
        LOGGER.info("Delete SMS response for %s ids: %s %s", len(ids), response.status_code, text[:500])
        normalized = text.lower().replace(" ", "")
        ok = response.ok and (
            not text
            or "success" in normalized
            or normalized in {"ok", "0", '{"result":"0"}', '{"result":0}'}
        )
        if not ok:
            return False, text or f"HTTP {response.status_code}"

        status_ok, status_text = self.wait_for_sms_command(sms_cmd="6")
        return status_ok, f"{text or f'HTTP {response.status_code}'}; status={status_text}"

    def wait_for_sms_command(self, sms_cmd: str, timeout_seconds: int = 45) -> tuple[bool, str]:
        deadline = time.monotonic() + timeout_seconds
        last_text = ""
        while time.monotonic() < deadline:
            try:
                data = self.get_cmd({"cmd": "sms_cmd_status_info", "sms_cmd": sms_cmd})
            except Exception as exc:
                last_text = str(exc)
                time.sleep(1)
                continue
            last_text = str(data)
            status = data.get("sms_cmd_status_result") or data.get("sms_cmd_status_info")
            if status == "3":
                return True, last_text
            if status == "2":
                return False, last_text
            time.sleep(1)
        return False, f"timeout; last={last_text}"
