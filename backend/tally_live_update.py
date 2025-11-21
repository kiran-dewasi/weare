from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional

import requests
import xml.etree.ElementTree as ET

from backend.tally_xml_builder import (
    LEDGER_ALLOWED_FIELDS,
    TallyXMLValidationError,
    build_ledger_update_xml,
    build_voucher_create_xml,
    build_voucher_update_xml,
)

logger = logging.getLogger("tally_live_update")
logging.basicConfig(level=logging.INFO)


class TallyAPIError(RuntimeError):
    """Raised when Tally responds with an error."""

    def __init__(self, message: str, response: Optional[TallyResponse] = None):
        super().__init__(message)
        self.response = response


class TallyIgnoredError(TallyAPIError):
    """Raised when Tally silently ignores a payload."""


@dataclass
class TallyResponse:
    raw_xml: str
    status: str = "UNKNOWN"
    created: int = 0
    altered: int = 0
    deleted: int = 0
    errors: list[str] = field(default_factory=list)
    is_ignored: bool = False

    @property
    def succeeded(self) -> bool:
        return not self.errors and not self.is_ignored

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "created": self.created,
            "altered": self.altered,
            "deleted": self.deleted,
            "errors": self.errors,
            "is_ignored": self.is_ignored,
            "raw_xml": self.raw_xml,
        }


def _safe_int(text: Optional[str]) -> int:
    if text is None:
        return 0
    try:
        return int(text.strip())
    except (ValueError, TypeError, AttributeError):
        return 0


def _collect_errors(root: ET.Element) -> list[str]:
    errors: list[str] = []
    for tag in ("LINEERROR", "ERROR"):
        for node in root.findall(f".//{tag}"):
            if node.text and node.text.strip():
                errors.append(node.text.strip())
    return errors


def parse_tally_response(response_text: str) -> TallyResponse:
    try:
        root = ET.fromstring(response_text)
    except ET.ParseError:
        logger.warning("Tally response is not valid XML; returning raw response")
        return TallyResponse(raw_xml=response_text, status="UNKNOWN")

    status_text = (root.findtext(".//STATUS") or "").strip()
    response = TallyResponse(
        raw_xml=response_text,
        status=status_text or "UNKNOWN",
        created=_safe_int(root.findtext(".//CREATED")),
        altered=_safe_int(root.findtext(".//ALTERED")),
        deleted=_safe_int(root.findtext(".//DELETED")),
    )
    response.errors = _collect_errors(root)

    if not response.errors:
        ignored_texts = {"0", "ignored", "IGNORED"}
        if status_text and status_text.lower() in ignored_texts:
            response.is_ignored = True
        elif not status_text and response.created == response.altered == response.deleted == 0:
            response.is_ignored = True

    return response


def post_to_tally(
    xml_data: str,
    tally_url: str = "http://localhost:9000",
    timeout: int = 15,
    session: Optional[requests.Session] = None,
) -> TallyResponse:
    if not xml_data or not xml_data.strip():
        raise TallyXMLValidationError("XML payload cannot be empty")

    client = session or requests
    
    headers = {"Content-Type": "text/xml; charset=utf-8"}
    try:
        logger.info("Posting XML payload to Tally at %s", tally_url)
        logger.debug("Outbound XML (first 1000 chars): %s", xml_data[:1000])
        resp = client.post(
            tally_url,
            data=xml_data.encode("utf-8"),
            headers=headers,
            timeout=timeout,
        )
        resp.raise_for_status()
        response = parse_tally_response(resp.text)
        logger.debug("Inbound XML (first 1000 chars): %s", resp.text[:1000])
        if response.errors:
            message = "; ".join(response.errors)
            logger.error("Tally reported errors: %s", message)
            raise TallyAPIError(message, response=response)
        if response.is_ignored:
            logger.error("Tally ignored the update (status=%s)", response.status)
            raise TallyIgnoredError("Tally ignored the update", response=response)
        logger.info(
            "Tally update succeeded (created=%s, altered=%s, deleted=%s)",
            response.created,
            response.altered,
            response.deleted,
        )
        return response
    except requests.Timeout as exc:
        logger.error("Timeout while posting to Tally at %s", tally_url)
        raise TallyAPIError(f"Tally API request timed out after {timeout} seconds") from exc
    except requests.ConnectionError as exc:
        logger.error("Connection error while posting to Tally: %s", exc)
        raise TallyAPIError(f"Could not connect to Tally at {tally_url}") from exc
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response else "unknown"
        sample = exc.response.text[:500] if exc.response and exc.response.text else ""
        logger.error("HTTP error while posting to Tally: %s - %s", status_code, sample)
        raise TallyAPIError(f"Tally API returned HTTP error: {status_code}") from exc
    except requests.RequestException as exc:
        logger.error("Request error while posting to Tally: %s", exc)
        raise TallyAPIError(f"Tally API request failed: {exc}") from exc


def _sanitize_ledger_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
    sanitized: Dict[str, Any] = {}
    invalid: list[str] = []
    for key, value in fields.items():
        upper = key.upper()
        if upper not in LEDGER_ALLOWED_FIELDS:
            invalid.append(key)
            continue
        sanitized[upper] = value
    if invalid:
        # Instead of bare raising, produce a rich error dict for API use
        raise TallyXMLValidationError({
            "status": "error",
            "message": f"Unsupported ledger fields for Tally update: {', '.join(sorted(set(invalid)))}",
            "allowed_fields": sorted(list(LEDGER_ALLOWED_FIELDS)),
            "invalid_fields": invalid
        })
    return sanitized


def update_ledger_in_tally(
    company_name: str,
    ledger_name: str,
    field_updates: Dict[str, Any],
    tally_url: str = "http://localhost:9000",
    timeout: int = 15,
    session: Optional[requests.Session] = None,
) -> TallyResponse:
    if not isinstance(field_updates, dict):
        raise TallyXMLValidationError("field_updates must be a dictionary")
    try:
        sanitized = _sanitize_ledger_fields(field_updates)
    except TallyXMLValidationError as e:
        # When catching TallyXMLValidationError, pass along any dict error as-is in the HTTPException detail.
        raise e
    if not sanitized:
        raise TallyXMLValidationError(
            "No valid ledger fields supplied for update. "
            f"Allowed fields: {sorted(LEDGER_ALLOWED_FIELDS)}"
        )
    logger.info(
        "Preparing ledger update for '%s' in company '%s' with fields %s",
        ledger_name,
        company_name,
        sanitized,
    )
    xml = build_ledger_update_xml(company_name, ledger_name, sanitized)
    return post_to_tally(xml, tally_url=tally_url, timeout=timeout, session=session)


def create_voucher_in_tally(
    company_name: str,
    voucher_fields: Dict[str, Any],
    line_items: Iterable[Dict[str, Any]],
    tally_url: str = "http://localhost:9000",
    timeout: int = 15,
    session: Optional[requests.Session] = None,
) -> TallyResponse:
    logger.info(
        "Preparing voucher creation for company '%s' (type=%s, party=%s)",
        company_name,
        voucher_fields.get("VOUCHERTYPENAME") or voucher_fields.get("voucher_type"),
        voucher_fields.get("PARTYLEDGERNAME") or voucher_fields.get("party_ledger"),
    )
    xml = build_voucher_create_xml(company_name, voucher_fields, line_items)
    return post_to_tally(xml, tally_url=tally_url, timeout=timeout, session=session)


def alter_voucher_in_tally(
    company_name: str,
    voucher_fields: Dict[str, Any],
    line_items: Iterable[Dict[str, Any]],
    tally_url: str = "http://localhost:9000",
    timeout: int = 15,
    session: Optional[requests.Session] = None,
) -> TallyResponse:
    logger.info(
        "Preparing voucher alteration for company '%s' (type=%s, party=%s)",
        company_name,
        voucher_fields.get("VOUCHERTYPENAME") or voucher_fields.get("voucher_type"),
        voucher_fields.get("PARTYLEDGERNAME") or voucher_fields.get("party_ledger"),
    )
    xml = build_voucher_update_xml(company_name, voucher_fields, line_items)
    return post_to_tally(xml, tally_url=tally_url, timeout=timeout, session=session)


def dispatch_tally_update(
    entity_type: str,
    company_name: str,
    payload: Dict[str, Any],
    tally_url: str = "http://localhost:9000",
    timeout: int = 15,
    session: Optional[requests.Session] = None,
) -> TallyResponse:
    entity = (entity_type or "").lower()
    if entity == "ledger":
        ledger_name = payload.get("ledger_name")
        if not ledger_name:
            raise TallyXMLValidationError("ledger_name is required for ledger updates")
        field_updates = payload.get("fields") or payload.get("updates") or {}
        return update_ledger_in_tally(
            company_name,
            ledger_name,
            field_updates,
            tally_url=tally_url,
            timeout=timeout,
            session=session,
        )
    if entity == "voucher":
        action = (payload.get("action") or "create").lower()
        voucher_fields = payload.get("voucher") or payload.get("fields") or {}
        line_items = payload.get("line_items") or []
        if action == "create":
            return create_voucher_in_tally(
                company_name,
                voucher_fields,
                line_items,
                tally_url=tally_url,
                timeout=timeout,
                session=session,
            )
        if action in {"alter", "update"}:
            return alter_voucher_in_tally(
                company_name,
                voucher_fields,
                line_items,
                tally_url=tally_url,
                timeout=timeout,
                session=session,
            )
        raise TallyXMLValidationError(f"Unsupported voucher action '{action}'")
    raise TallyXMLValidationError(f"Unsupported Tally entity '{entity_type}'")
