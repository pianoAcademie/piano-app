from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notification_engine import JobRun, JobRunLog, MobilePushDevice, Notification
from app.models.user import User
from app.services.i18n import normalize_language
from app.services.mobile_push_provider import send_mobile_push


@dataclass(frozen=True)
class MobilePushSummary:
    requested_user_count: int
    device_count: int
    sent_count: int
    failed_count: int
    skipped_count: int
    details: list[str]
    job_run_id: UUID


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _localized_content(
    *,
    language: str,
    title_fr: str,
    body_fr: str,
    title_en: str | None,
    body_en: str | None,
) -> tuple[str, str]:
    if normalize_language(language) == "en":
        return ((title_en or title_fr).strip(), (body_en or body_fr).strip())
    return (title_fr.strip(), body_fr.strip())


def register_mobile_push_device(
    db: Session,
    *,
    user: User,
    installation_id: str,
    push_token: str,
    platform: str,
    app_target: str,
    permission_status: str,
    locale: str,
    app_version: str | None,
    device_label: str | None,
) -> MobilePushDevice:
    now = _utcnow()
    target = app_target.strip().upper()
    installation = installation_id.strip()
    token = push_token.strip()

    row = db.scalar(
        select(MobilePushDevice)
        .where(
            MobilePushDevice.app_target == target,
            MobilePushDevice.installation_id == installation,
        )
        .with_for_update()
    )
    token_owner = db.scalar(
        select(MobilePushDevice)
        .where(
            MobilePushDevice.app_target == target,
            MobilePushDevice.push_token == token,
        )
        .with_for_update()
    )
    if token_owner is not None and (row is None or token_owner.id != row.id):
        db.delete(token_owner)
        db.flush()

    if row is None:
        row = MobilePushDevice(
            user_id=user.id,
            app_target=target,
            platform=platform.strip().upper(),
            installation_id=installation,
            push_token=token,
        )
    row.user_id = user.id
    row.platform = platform.strip().upper()
    row.push_token = token
    row.permission_status = permission_status.strip().upper() or "GRANTED"
    row.locale = normalize_language(locale)
    row.app_version = (app_version or "").strip() or None
    row.device_label = (device_label or "").strip() or None
    row.is_enabled = True
    row.revoked_at = None
    row.last_registered_at = now
    row.last_seen_at = now
    row.updated_at = now
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def disable_mobile_push_device(
    db: Session,
    *,
    user_id: UUID,
    installation_id: str,
    app_target: str,
) -> bool:
    row = db.scalar(
        select(MobilePushDevice)
        .where(
            MobilePushDevice.user_id == user_id,
            MobilePushDevice.app_target == app_target.strip().upper(),
            MobilePushDevice.installation_id == installation_id.strip(),
        )
        .with_for_update()
    )
    if row is None:
        return False
    now = _utcnow()
    row.is_enabled = False
    row.permission_status = "DENIED"
    row.revoked_at = now
    row.updated_at = now
    db.add(row)
    db.commit()
    return True


def send_mobile_push_to_users(
    db: Session,
    *,
    user_ids: set[UUID],
    title_fr: str,
    body_fr: str,
    title_en: str | None,
    body_en: str | None,
    deep_link: str | None,
    source: str,
    related_entity_type: str,
    related_entity_id: UUID,
    actor_id: UUID | None,
    slot_id: UUID | None = None,
    app_target: str = "CLIENT",
) -> MobilePushSummary:
    now = _utcnow()
    normalized_app_target = (app_target or "CLIENT").strip().upper()
    if normalized_app_target not in {"CLIENT", "PROF"}:
        raise ValueError("Unsupported mobile push app target")
    fallback_deep_link = "/prof?tab=messages" if normalized_app_target == "PROF" else "/client"
    normalized_user_ids = set(user_ids)
    run = JobRun(
        job_name="admin_mobile_push",
        job_key=str(related_entity_id),
        triggered_by="admin",
        started_at=now,
        status="running",
        items_scanned=len(normalized_user_ids),
        metadata_json={
            "source": source,
            "related_entity_type": related_entity_type,
            "related_entity_id": str(related_entity_id),
            "actor_id": str(actor_id) if actor_id else None,
            "app_target": normalized_app_target,
        },
    )
    db.add(run)
    db.flush()

    rows = db.execute(
        select(MobilePushDevice, User)
        .join(User, User.id == MobilePushDevice.user_id)
        .where(
            MobilePushDevice.user_id.in_(normalized_user_ids),
            MobilePushDevice.app_target == normalized_app_target,
            MobilePushDevice.is_enabled.is_(True),
            MobilePushDevice.permission_status == "GRANTED",
            User.is_active.is_(True),
        )
        .order_by(MobilePushDevice.user_id.asc(), MobilePushDevice.created_at.asc())
    ).all() if normalized_user_ids else []

    device_user_ids = {user.id for _, user in rows}
    missing_users = len(normalized_user_ids - device_user_ids)
    sent_count = 0
    failed_count = 0
    details: list[str] = []

    for device, user in rows:
        title, body = _localized_content(
            language=user.preferred_language or device.locale,
            title_fr=title_fr,
            body_fr=body_fr,
            title_en=title_en,
            body_en=body_en,
        )
        notification = Notification(
            notification_type="ADMIN_MOBILE_PUSH",
            channel="PUSH",
            dispatch_mode="IMMEDIATE",
            source=source,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
            slot_id=slot_id,
            recipient_type="USER",
            recipient_contact_id=user.id,
            recipient_device_id=device.id,
            subject=title,
            body_snapshot=body,
            payload_snapshot={
                "deep_link": deep_link or fallback_deep_link,
                "platform": device.platform,
                "installation_id": device.installation_id,
                "language": normalize_language(user.preferred_language or device.locale),
                "app_target": normalized_app_target,
            },
            idempotency_key=f"ADMIN_MOBILE_PUSH:{run.id}:{device.id}:{uuid4()}",
            scheduled_for=now,
            status="pending",
            job_run_id=run.id,
            created_at=now,
            updated_at=now,
        )
        db.add(notification)
        db.flush()

        provider_result = send_mobile_push(
            platform=device.platform,
            token=device.push_token,
            title=title,
            body=body,
            data={
                "notification_id": str(notification.id),
                "deep_link": deep_link or fallback_deep_link,
                "source": source,
            },
        )
        notification.provider_name = provider_result.provider_name
        notification.provider_message_id = provider_result.provider_message_id
        notification.provider_status = provider_result.provider_status
        notification.updated_at = _utcnow()
        if provider_result.accepted:
            notification.status = "sent"
            notification.sent_at = notification.updated_at
            sent_count += 1
        else:
            notification.status = "failed"
            notification.failed_at = notification.updated_at
            notification.failure_reason = provider_result.error_message
            failed_count += 1
            details.append(
                f"{user.email} ({device.platform}): {provider_result.error_message or provider_result.provider_status or 'echec'}"
            )
            if provider_result.invalid_token:
                device.is_enabled = False
                device.permission_status = "INVALID_TOKEN"
                device.revoked_at = notification.updated_at
                device.updated_at = notification.updated_at
                db.add(device)
        db.add(notification)

    finished_at = _utcnow()
    run.finished_at = finished_at
    run.status = "success" if failed_count == 0 else ("partial" if sent_count > 0 else "failed")
    run.items_processed = len(rows)
    run.items_sent = sent_count
    run.items_skipped = missing_users
    run.items_failed = failed_count
    run.summary_text = (
        f"Push mobile: {sent_count} envoye(s), {failed_count} echec(s), "
        f"{missing_users} utilisateur(s) sans appareil actif"
    )
    db.add(run)
    db.add(
        JobRunLog(
            job_run_id=run.id,
            level="INFO" if failed_count == 0 else "WARNING",
            message=run.summary_text,
            context_json={"details": details[:100]},
        )
    )
    db.commit()

    return MobilePushSummary(
        requested_user_count=len(normalized_user_ids),
        device_count=len(rows),
        sent_count=sent_count,
        failed_count=failed_count,
        skipped_count=missing_users,
        details=details,
        job_run_id=run.id,
    )


def record_mobile_push_event(
    db: Session,
    *,
    notification_id: UUID,
    user_id: UUID,
    event: str,
) -> Notification | None:
    notification = db.scalar(
        select(Notification)
        .where(
            Notification.id == notification_id,
            Notification.channel == "PUSH",
            Notification.recipient_contact_id == user_id,
        )
        .with_for_update()
    )
    if notification is None:
        return None
    now = _utcnow()
    if event.strip().upper() == "OPENED":
        notification.opened_at = notification.opened_at or now
        notification.received_at = notification.received_at or now
        notification.provider_status = "OPENED"
    else:
        notification.received_at = notification.received_at or now
        if notification.provider_status != "OPENED":
            notification.provider_status = "RECEIVED"
    notification.updated_at = now
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


__all__ = [
    "MobilePushSummary",
    "disable_mobile_push_device",
    "record_mobile_push_event",
    "register_mobile_push_device",
    "send_mobile_push_to_users",
]
