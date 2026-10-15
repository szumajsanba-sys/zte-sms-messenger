from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from .models import DecodeResult, DecodedSms

HEX_RE = re.compile(r"^[0-9a-fA-F]+$")


def read_text_file(path: str) -> str:
    raw = open(path, "rb").read()
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "cp1251"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def extract_json_text(text: str) -> str:
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Ответ роутера не похож на JSON: объект не найден.")
    text = text[start : end + 1]
    return "".join(ch for ch in text if ch in "\n\r\t" or ord(ch) >= 32)


def parse_json_response(text: str) -> dict[str, Any]:
    return json.loads(extract_json_text(text), strict=False)


def printable_ratio(value: str) -> float:
    if not value:
        return 1.0
    return sum(ch.isprintable() or ch.isspace() for ch in value) / len(value)


def looks_like_hex(value: str) -> bool:
    cleaned = re.sub(r"\s+", "", value or "")
    return bool(cleaned) and len(cleaned) % 2 == 0 and bool(HEX_RE.fullmatch(cleaned))


def decode_possible_hex(value: Any, preserve_short_numeric: bool = False) -> str:
    if value is None:
        return ""

    original = str(value).strip()
    if not original:
        return ""
    if preserve_short_numeric and original.isdigit() and len(original) <= 8:
        return original

    cleaned = re.sub(r"\s+", "", original)
    if not looks_like_hex(cleaned):
        return original

    try:
        raw = bytes.fromhex(cleaned)
    except ValueError:
        return original

    candidates: list[str] = []
    for encoding in ("utf-16-be", "utf-16-le", "utf-8"):
        try:
            decoded = raw.decode(encoding).replace("\ufeff", "").strip("\x00").strip()
        except UnicodeDecodeError:
            continue
        if decoded and printable_ratio(decoded) >= 0.85:
            candidates.append(decoded)

    return candidates[0] if candidates else original


def parse_zte_date(date_str: Any) -> str | None:
    if not date_str:
        return None
    parts = str(date_str).split(",")
    if len(parts) < 6:
        return None
    try:
        year = 2000 + int(parts[0])
        dt = datetime(
            year,
            int(parts[1]),
            int(parts[2]),
            int(parts[3]),
            int(parts[4]),
            int(parts[5]),
        )
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


def normalize_sender(value: str) -> str:
    normalized = re.sub(r"\s+", " ", (value or "").strip())
    if normalized.startswith("+"):
        return "+" + re.sub(r"\D+", "", normalized)
    digits = re.sub(r"\D+", "", normalized)
    return digits if len(digits) >= 7 else normalized.casefold()


def build_source_hash(
    message: dict[str, Any],
    mem_store: int,
    decoded_sender: str,
    decoded_content: str,
    received_at: str | None,
) -> str:
    payload = {
        "sender": normalize_sender(decoded_sender),
        "decoded_content": decoded_content,
        "received_at": received_at or "",
        "mem_store": mem_store,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class SmsDecoder:
    def decode_response_text(self, text: str, mem_store: int = 1) -> DecodeResult:
        data = parse_json_response(text)
        messages = data.get("messages", [])
        if not isinstance(messages, list):
            raise ValueError("В JSON нет массива messages.")
        return self.decode_messages(messages, mem_store=mem_store)

    def decode_file(self, path: str, mem_store: int = 1) -> DecodeResult:
        return self.decode_response_text(read_text_file(path), mem_store=mem_store)

    def decode_messages(self, messages: list[dict[str, Any]], mem_store: int = 1) -> DecodeResult:
        decoded: list[DecodedSms] = []
        warnings: list[str] = []
        suspicious_count = 0

        for raw_msg in messages:
            if not isinstance(raw_msg, dict):
                warnings.append("Пропущена запись SMS не-объектного типа.")
                suspicious_count += 1
                continue

            sender_raw = str(raw_msg.get("number", "") or "")
            content_raw = str(raw_msg.get("content", "") or "")
            sender_decoded = decode_possible_hex(sender_raw, preserve_short_numeric=True)
            content_decoded = decode_possible_hex(content_raw)
            received_at = parse_zte_date(raw_msg.get("date", ""))
            item_warnings: list[str] = []

            if content_raw and not content_decoded:
                item_warnings.append("Текст SMS стал пустым после декодирования.")
            if content_decoded and printable_ratio(content_decoded) < 0.85:
                item_warnings.append("В декодированном тексте много непечатаемых символов.")
            if raw_msg.get("date") and not received_at:
                item_warnings.append("Не удалось разобрать дату ZTE.")

            suspicious_count += len(item_warnings)
            decoded.append(
                DecodedSms(
                    zte_id=str(raw_msg.get("id", "") or ""),
                    sender_raw=sender_raw,
                    sender_decoded=sender_decoded,
                    content_raw=content_raw,
                    content_decoded=content_decoded,
                    zte_date_raw=str(raw_msg.get("date", "") or ""),
                    received_at=received_at,
                    mem_store=mem_store,
                    raw_json=raw_msg,
                    source_hash=build_source_hash(raw_msg, mem_store, sender_decoded, content_decoded, received_at),
                    warnings=item_warnings,
                )
            )

        if messages and len(decoded) < max(1, len(messages) // 2):
            warnings.append("Декодировалось подозрительно мало сообщений.")
        for msg in decoded:
            warnings.extend(f"SMS {msg.zte_id}: {warning}" for warning in msg.warnings)

        return DecodeResult(messages=decoded, warnings=warnings, suspicious=bool(warnings or suspicious_count))
