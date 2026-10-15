from __future__ import annotations

import base64
import hashlib
import logging
from dataclasses import dataclass
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class AuthResult:
    ok: bool
    message: str
    method: str = "none"


class ZteAuth:
    def __init__(self, session: requests.Session, base_url: str, password: str, timeout: int = 30) -> None:
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.password = password
        self.timeout = timeout

    def ensure_authenticated(self) -> AuthResult:
        if self.is_logged_in():
            return AuthResult(True, "Уже авторизовано", "existing-session")

        for method in (self._login_zte_sha256_base64, self._login_plain, self._login_base64, self._login_sha256_upper):
            try:
                result = method()
            except requests.RequestException as exc:
                LOGGER.warning("ZTE auth method failed: %s", exc)
                continue
            if result.ok and self.is_logged_in():
                return result

        return AuthResult(False, "Нужна авторизация или прошивка использует другой алгоритм входа.")

    def is_logged_in(self) -> bool:
        url = f"{self.base_url}/goform/goform_get_cmd_process"
        params = {"isTest": "false", "cmd": "loginfo"}
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            return response.ok and response.json().get("loginfo") == "ok"
        except requests.RequestException:
            return False
        except ValueError:
            return False

    def get_language_hash_params(self) -> tuple[str, str]:
        url = f"{self.base_url}/goform/goform_get_cmd_process"
        params = {
            "isTest": "false",
            "cmd": "Language,cr_version,wa_inner_version",
            "multi_data": "1",
        }
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        return data.get("wa_inner_version", ""), data.get("cr_version", "")

    def make_accessible_id(self) -> str:
        rd0, rd1 = self.get_language_hash_params()
        url = f"{self.base_url}/goform/goform_get_cmd_process"
        response = self.session.get(url, params={"isTest": "false", "cmd": "RD"}, timeout=self.timeout)
        response.raise_for_status()
        rd = response.json().get("RD", "")
        first = hashlib.md5((rd0 + rd1).encode("utf-8")).hexdigest()
        return hashlib.md5((first + rd).encode("utf-8")).hexdigest()

    def _post_login(self, payload: dict[str, Any], method: str) -> AuthResult:
        url = f"{self.base_url}/goform/goform_set_cmd_process"
        data = {"isTest": "false", "goformId": "LOGIN", **payload}
        response = self.session.post(url, data=data, timeout=self.timeout)
        LOGGER.info("Auth %s response: %s %s", method, response.status_code, response.text[:300])
        ok = response.ok and any(marker in response.text.lower() for marker in ("success", "result", "ok"))
        return AuthResult(ok, "Авторизация выполнена" if ok else "Метод входа не принят роутером", method)

    def _login_plain(self) -> AuthResult:
        return self._post_login({"password": self.password}, "plain")

    def _login_base64(self) -> AuthResult:
        encoded = base64.b64encode(self.password.encode("utf-8")).decode("ascii")
        return self._post_login({"password": encoded}, "base64")

    def _login_sha256_upper(self) -> AuthResult:
        digest = hashlib.sha256(self.password.encode("utf-8")).hexdigest().upper()
        return self._post_login({"password": digest}, "sha256-upper")

    def _login_zte_sha256_base64(self) -> AuthResult:
        encoded = base64.b64encode(self.password.encode("utf-8")).decode("ascii")
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest().upper()
        return self._post_login({"password": digest}, "sha256-base64")
