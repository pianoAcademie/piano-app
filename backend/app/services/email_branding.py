from __future__ import annotations

from html import escape
from urllib.parse import urlparse


def _safe_url(value: str | None) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    if "{" in raw and "}" in raw:
        return raw
    parsed = urlparse(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return raw


def render_branded_email(
    *,
    preview: str,
    eyebrow: str,
    title: str,
    greeting: str,
    intro: str,
    rows: list[tuple[str, str]] | tuple[tuple[str, str], ...] = (),
    message: str | None = None,
    button_url: str | None = None,
    button_label: str | None = None,
    links: list[tuple[str, str]] | tuple[tuple[str, str], ...] = (),
    footer: str = "Cet e-mail a été envoyé automatiquement par Piano Académie.",
) -> str:
    summary_rows = "".join(
        (
            '<tr>'
            f'<td style="padding:8px 12px 8px 20px;width:40%;font-size:13px;font-weight:700;color:#667085;">{escape(str(label))}</td>'
            f'<td style="padding:8px 20px 8px 12px;font-size:15px;font-weight:700;color:#172033;">{escape(str(value))}</td>'
            '</tr>'
        )
        for label, value in rows
    )
    summary_block = (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="margin:0;background:#f8fafc;border:1px solid #e3e7ee;border-radius:12px;">'
        f'{summary_rows}</table>'
        if summary_rows
        else ""
    )
    message_block = (
        '<div style="margin:22px 0 0;padding:18px 20px;background:#fff7e6;border:1px solid #edd7b3;border-radius:12px;">'
        f'<p style="margin:0;font-size:15px;line-height:23px;color:#5f4a2d;">{escape(message)}</p>'
        '</div>'
        if message
        else ""
    )
    safe_button_url = _safe_url(button_url)
    button_block = (
        '<table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" '
        'style="margin:22px auto 0 auto;"><tr><td style="border-radius:9px;background:#c98224;">'
        f'<a href="{escape(safe_button_url, quote=True)}" style="display:inline-block;padding:13px 22px;color:#ffffff;'
        f'text-decoration:none;font-size:15px;line-height:20px;font-weight:800;">{escape(button_label or "Ouvrir")}</a>'
        '</td></tr></table>'
        if safe_button_url and button_label
        else ""
    )
    safe_links = [(label, safe_url) for label, url in links if (safe_url := _safe_url(url)) is not None]
    links_block = (
        '<div style="margin:20px 0 0;font-size:14px;line-height:22px;color:#5f6673;">'
        + "".join(
            f'<div><a href="{escape(url, quote=True)}" style="color:#8a5a12;text-decoration:underline;">{escape(label)}</a></div>'
            for label, url in safe_links
        )
        + '</div>'
        if safe_links
        else ""
    )
    return (
        '<!doctype html><html><body style="margin:0;padding:0;background:#f2f4f7;">'
        '<div style="display:none;max-height:0;overflow:hidden;opacity:0;">'
        f'{escape(preview)}</div>'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f2f4f7;">'
        '<tr><td align="center" style="padding:24px 12px;">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="max-width:620px;background:#ffffff;border:1px solid #e3e7ee;border-radius:16px;overflow:hidden;">'
        '<tr><td style="padding:28px 30px;background:#172033;">'
        '<div style="font-size:13px;line-height:18px;font-weight:800;letter-spacing:1.5px;color:#e4b85d;">PIANO ACADÉMIE</div>'
        f'<div style="margin-top:8px;font-size:12px;line-height:18px;font-weight:700;letter-spacing:1px;color:#e4b85d;">{escape(eyebrow)}</div>'
        f'<div style="margin-top:5px;font-size:28px;line-height:35px;font-weight:800;color:#ffffff;">{escape(title)}</div>'
        '</td></tr>'
        '<tr><td style="padding:28px 30px 30px 30px;">'
        f'<p style="margin:0 0 10px 0;font-size:17px;line-height:25px;color:#172033;">{escape(greeting)}</p>'
        f'<p style="margin:0 0 22px 0;font-size:15px;line-height:23px;color:#5f6673;">{escape(intro)}</p>'
        f'{summary_block}{message_block}{button_block}{links_block}'
        f'<p style="margin:22px 0 0;font-size:12px;line-height:19px;color:#7b8494;text-align:center;">{escape(footer)}</p>'
        '</td></tr></table>'
        '</td></tr></table></body></html>'
    )


__all__ = ["render_branded_email"]
