"""Connectors component: outbound email for now. Every message is recorded in
outbound_messages whichever transport delivers it.

FACTORY_EMAIL_TRANSPORT=sandbox (default) records without sending, for tests and demos.
FACTORY_EMAIL_TRANSPORT=gmail sends through the Gmail API with the tenant's OAuth token,
which a token provider reads from Supabase Vault."""
from __future__ import annotations

import base64
import os
from email.message import EmailMessage
from typing import Callable

import httpx

from factory.models import OutboundMessage

# Set by the deployment: (tenant_id, connector) -> OAuth access token from Supabase Vault.
token_provider: Callable[[object, str], str] | None = None


class EmailClient:
    def __init__(self, ctx, transport: str):
        self.ctx = ctx
        self.transport = transport

    def send(self, to: str, subject: str, body: str) -> OutboundMessage:
        status = "sandboxed"
        if self.transport == "gmail":
            self._send_gmail(to, subject, body)
            status = "sent"
        msg = OutboundMessage(tenant_id=self.ctx.tenant_id, connector=f"email:{self.transport}",
                              to=to, subject=subject, body=body, status=status)
        self.ctx.db.add(msg)
        return msg

    def _send_gmail(self, to: str, subject: str, body: str) -> None:
        if token_provider is None:
            raise RuntimeError("gmail transport needs factory.components.connectors.token_provider")
        mime = EmailMessage()
        mime["To"], mime["Subject"] = to, subject
        mime.set_content(body)
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
        r = httpx.post("https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                       headers={"Authorization": f"Bearer {token_provider(self.ctx.tenant_id, 'email')}"},
                       json={"raw": raw}, timeout=20)
        r.raise_for_status()


def email_client(ctx) -> EmailClient:
    return EmailClient(ctx, os.environ.get("FACTORY_EMAIL_TRANSPORT", "sandbox"))
