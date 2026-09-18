"""Tests for the pure EmailMessage → Communication mapping."""

from frappe_salesforce.sync.transforms import (
    _to_frappe_addresses,
    build_communication_values,
)

SENT_EMAIL = {
    "Subject": "Re: Concept Notes - Aug 2026",
    "TextBody": "Hi both,\nAttached as discussed.",
    "HtmlBody": "<p>Hi both,</p><p>Attached as discussed.</p>",
    "FromAddress": "grants@peas.org.uk",
    "FromName": "PEAS Grants",
    "ToAddress": "kate.obrien@costafoundation.com; faye.southey@costafoundation.com",
    "CcAddress": None,
    "BccAddress": "",
    "MessageDate": "2026-08-26T14:03:00.000+0000",
    "Incoming": False,
    "RelatedToId": "006D000000abcdeIAA",
}


def test_sent_email_maps_to_communication():
    v = build_communication_values(SENT_EMAIL)
    assert v["communication_type"] == "Communication"
    assert v["communication_medium"] == "Email"
    assert v["sent_or_received"] == "Sent"
    assert v["subject"] == "Re: Concept Notes - Aug 2026"
    assert v["content"] == SENT_EMAIL["HtmlBody"]
    assert v["sender"] == "grants@peas.org.uk"
    assert v["recipients"] == (
        "kate.obrien@costafoundation.com, faye.southey@costafoundation.com"
    )
    assert v["cc"] is None and v["bcc"] is None
    assert v["communication_date"] == "2026-08-26 14:03:00"


def test_incoming_email_is_received():
    v = build_communication_values({**SENT_EMAIL, "Incoming": True})
    assert v["sent_or_received"] == "Received"


def test_text_only_body_is_escaped_html():
    v = build_communication_values(
        {**SENT_EMAIL, "HtmlBody": None, "TextBody": "1 < 2\nnew line & so on"}
    )
    assert v["content"] == "1 &lt; 2<br>new line &amp; so on"
    assert v["text_content"] == "1 < 2\nnew line & so on"


def test_missing_subject_gets_placeholder():
    assert build_communication_values({})["subject"] == "(no subject)"


def test_address_separator_conversion():
    assert _to_frappe_addresses("a@x.com;b@y.com ; c@z.com") == (
        "a@x.com, b@y.com, c@z.com"
    )
    assert _to_frappe_addresses("") is None
    assert _to_frappe_addresses(None) is None
