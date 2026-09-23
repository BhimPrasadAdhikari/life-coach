"""
interfaces/whatsapp/app.py — FastAPI Webhook adapter for WhatsApp (Meta Cloud API / Twilio).
"""
from __future__ import annotations
import hmac
import hashlib
import logging
from typing import Any

import httpx
from fastapi import APIRouter, Request, HTTPException, Response, Query
from interfaces._base import AgentRequest, AgentResponse, MediaAttachment
from core.cache import get_redis_cache
from core.config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_WHATSAPP_FROM,
    WHATSAPP_ACCESS_TOKEN,
    WHATSAPP_API_VERSION,
    WHATSAPP_HTTP_TIMEOUT,
    WHATSAPP_PHONE_NUMBER_ID,
    WHATSAPP_PROVIDER,
    WHATSAPP_VERIFY_TOKEN,
    WHATSAPP_APP_SECRET,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])


def verify_meta_signature(payload: bytes, signature_header: str, app_secret: str) -> bool:
    """
    Verify X-Hub-Signature-256 header sent by Meta Cloud API.
    """
    if not signature_header or not app_secret:
        return True
    
    parts = signature_header.split("=")
    if len(parts) != 2 or parts[0] != "sha256":
        return False
    
    expected_sig = parts[1]
    computed_sig = hmac.new(
        app_secret.encode("utf-8"),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(computed_sig, expected_sig)


def parse_whatsapp_payload(payload: dict[str, Any]) -> AgentRequest:
    """
    Normalizes Meta Cloud API, Twilio, or generic WhatsApp payload into AgentRequest.
    """
    sender = "unknown"
    content = ""
    media = []

    # 1. Meta Cloud API Payload format
    if "entry" in payload and isinstance(payload["entry"], list) and len(payload["entry"]) > 0:
        entry = payload["entry"][0]
        changes = entry.get("changes", [])
        if changes and isinstance(changes, list):
            value = changes[0].get("value", {})
            messages = value.get("messages", [])
            if messages:
                msg = messages[0]
                sender = msg.get("from", "unknown")
                msg_type = msg.get("type", "text")
                
                if msg_type == "text":
                    content = msg.get("text", {}).get("body", "")
                elif msg_type == "image":
                    img = msg.get("image", {})
                    content = img.get("caption", "[Image attached]")
                    media.append(MediaAttachment(type="image", url=img.get("id"), mime_type=img.get("mime_type")))
                elif msg_type == "audio":
                    aud = msg.get("audio", {})
                    content = "[Audio attached]"
                    media.append(MediaAttachment(type="audio", url=aud.get("id"), mime_type=aud.get("mime_type")))

    # 2. Twilio Webhook format (JSON or mapped dict)
    elif "From" in payload or "Body" in payload:
        raw_from = payload.get("From", "unknown")
        sender = raw_from.replace("whatsapp:", "").strip()
        content = payload.get("Body", "")
        if "MediaUrl0" in payload:
            media.append(MediaAttachment(
                type="image" if "image" in payload.get("MediaContentType0", "") else "media",
                url=payload.get("MediaUrl0"),
                mime_type=payload.get("MediaContentType0")
            ))

    # 3. Simple / Direct format
    else:
        sender = payload.get("from", payload.get("user_id", "unknown"))
        if isinstance(payload.get("text"), dict):
            content = payload["text"].get("body", "")
        else:
            content = str(payload.get("content", payload.get("text", "")))

    sender = str(sender).replace("+", "").replace(" ", "")
    user_id = f"wa_{sender}"
    thread_id = f"thread_{sender}"

    return AgentRequest(
        user_id=user_id,
        thread_id=thread_id,
        content=content,
        media=media,
        channel="whatsapp",
        metadata={"raw_payload": payload}
    )


async def dispatch_graph_request(agent_req: AgentRequest) -> AgentResponse:
    """
    Invokes the shared graph service for an AgentRequest.
    """
    from services.graph_service import graph_service

    result_state = await graph_service.invoke_graph(
        content=agent_req.content,
        thread_id=agent_req.thread_id,
        model_key=agent_req.model_key,
        user_id=agent_req.user_id,
        channel=agent_req.channel,
    )

    messages = result_state.get("messages", [])
    last_response = ""
    if messages:
        last_msg = messages[-1]
        last_response = getattr(last_msg, "content", str(last_msg))

    return AgentResponse(
        user_id=agent_req.user_id,
        thread_id=agent_req.thread_id,
        content=last_response,
        workflow=result_state.get("workflow", "conversation"),
        media_url=result_state.get("media_url"),
        metadata={"evolution_pending": result_state.get("evolution_pending", False)}
    )


def _public_media_url(response: AgentResponse) -> str | None:
    """Return media only when a provider can fetch it over HTTP(S)."""
    if response.media_url and response.media_url.startswith(("https://", "http://")):
        return response.media_url
    return None


def _recipient_phone(to_user: str) -> str:
    """Convert an internal WhatsApp user ID into an E.164-like phone value."""
    recipient = to_user.removeprefix("wa_").removeprefix("whatsapp:")
    return recipient if recipient.startswith("+") else f"+{recipient}"


def _meta_payload(to_user: str, response: AgentResponse) -> dict[str, Any]:
    media_url = _public_media_url(response)
    if media_url and response.workflow in {"audio", "image"}:
        media_type = "audio" if response.workflow == "audio" else "image"
        message: dict[str, Any] = {media_type: {"link": media_url}}
        if media_type == "image" and response.content:
            message[media_type]["caption"] = response.content
    else:
        message = {"text": {"preview_url": False, "body": response.content}}

    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": _recipient_phone(to_user).lstrip("+"),
        "type": next(iter(message)),
        **message,
    }


def _twilio_data(to_user: str, response: AgentResponse) -> dict[str, Any]:
    data = {
        "From": TWILIO_WHATSAPP_FROM,
        "To": f"whatsapp:{_recipient_phone(to_user)}",
        "Body": response.content,
    }
    media_url = _public_media_url(response)
    if media_url and response.workflow in {"audio", "image"}:
        data["MediaUrl"] = media_url
    return data


async def _send_meta_message(to_user: str, response: AgentResponse) -> dict[str, Any]:
    if not WHATSAPP_PHONE_NUMBER_ID or not WHATSAPP_ACCESS_TOKEN:
        raise RuntimeError(
            "Meta WhatsApp outbound messaging requires WHATSAPP_PHONE_NUMBER_ID "
            "and WHATSAPP_ACCESS_TOKEN"
        )

    url = (
        f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/"
        f"{WHATSAPP_PHONE_NUMBER_ID}/messages"
    )
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=WHATSAPP_HTTP_TIMEOUT) as client:
        result = await client.post(url, headers=headers, json=_meta_payload(to_user, response))
    result.raise_for_status()
    return {"status": "sent", "provider": "meta", "to": to_user, "provider_response": result.json()}


async def _send_twilio_message(to_user: str, response: AgentResponse) -> dict[str, Any]:
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_WHATSAPP_FROM:
        raise RuntimeError(
            "Twilio WhatsApp outbound messaging requires TWILIO_ACCOUNT_SID, "
            "TWILIO_AUTH_TOKEN, and TWILIO_WHATSAPP_FROM"
        )

    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    async with httpx.AsyncClient(timeout=WHATSAPP_HTTP_TIMEOUT) as client:
        result = await client.post(
            url,
            data=_twilio_data(to_user, response),
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
        )
    result.raise_for_status()
    return {"status": "sent", "provider": "twilio", "to": to_user, "provider_response": result.json()}


async def send_whatsapp_response(to_user: str, response: AgentResponse) -> dict[str, Any]:
    """Deliver an outbound WhatsApp message through Meta Cloud API or Twilio."""
    if WHATSAPP_PROVIDER == "meta":
        return await _send_meta_message(to_user, response)
    if WHATSAPP_PROVIDER == "twilio":
        return await _send_twilio_message(to_user, response)
    raise RuntimeError(f"Unsupported WHATSAPP_PROVIDER: {WHATSAPP_PROVIDER}")


@router.get("/webhook")
async def verify_webhook(
    request: Request,
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
):
    """
    Handles Meta Cloud API / Twilio challenge verification GET requests.
    """
    params = request.query_params
    mode = hub_mode or params.get("hub.mode")
    verify_token = hub_verify_token or params.get("hub.verify_token")
    challenge = hub_challenge or params.get("hub.challenge")

    if mode == "subscribe" or verify_token:
        if verify_token == WHATSAPP_VERIFY_TOKEN:
            if challenge:
                try:
                    return Response(content=str(int(challenge)), media_type="text/plain")
                except ValueError:
                    return Response(content=str(challenge), media_type="text/plain")
            return Response(content="SUCCESS", media_type="text/plain")
        raise HTTPException(status_code=403, detail="Invalid verify token")

    return {"status": "ok", "message": "WhatsApp webhook endpoint operational."}


@router.post("/webhook")
async def handle_whatsapp_message(request: Request):
    """
    Handles inbound POST messages from Meta Cloud API or Twilio.
    Normalizes payload into AgentRequest, runs graph turn, and returns response.
    """
    body = await request.body()
    
    # Verify signature if Meta App Secret is set
    if WHATSAPP_APP_SECRET:
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not verify_meta_signature(body, signature, WHATSAPP_APP_SECRET):
            raise HTTPException(status_code=401, detail="Invalid Meta signature")

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {exc}")

    agent_req = parse_whatsapp_payload(payload)

    cache = get_redis_cache()
    raw_payload = agent_req.metadata.get("raw_payload", {})
    meta_messages = raw_payload.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {}).get("messages", [{}])
    event_id = (
        raw_payload.get("MessageSid")
        or raw_payload.get("SmsMessageSid")
        or (meta_messages[0].get("id") if meta_messages else None)
    )
    if event_id and not cache.claim_idempotency(f"whatsapp:{event_id}"):
        return {"status": "duplicate", "event_id": event_id}
    if not cache.allow_request(agent_req.user_id):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    # Process message through LangGraph orchestrator
    agent_resp = await dispatch_graph_request(agent_req)
    
    # Outbound response dispatch
    try:
        dispatch_status = await send_whatsapp_response(agent_req.user_id, agent_resp)
    except (httpx.HTTPError, RuntimeError) as exc:
        logger.error("WhatsApp outbound delivery failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="WhatsApp response delivery failed") from exc

    return {
        "status": "processed",
        "request": agent_req.model_dump(),
        "response": agent_resp.model_dump(),
        "dispatch": dispatch_status,
    }
