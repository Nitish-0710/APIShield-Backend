from datetime import datetime, timedelta, timezone
import hashlib
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session

from app.core.errors import AppException
from app.models.ml import AlertRecord


class AlertService:
    def create_alert_if_due(
        self,
        db: Session,
        user_id: str,
        api_id: Optional[str],
        title: str,
        description: str,
        severity: str,
        source: str,
        condition_key: str,
        cooldown_minutes: int = 15,
    ) -> Optional[AlertRecord]:
        """
        Creates an alert if an open alert with the same condition fingerprint
        was not created within the cooldown window. Prevents alert storms.
        """
        fingerprint = hashlib.sha256(f"{api_id or 'global'}:{condition_key}".encode()).hexdigest()[:32]

        now = datetime.now(timezone.utc)
        cooldown_cutoff = now - timedelta(minutes=cooldown_minutes)

        recent_existing = (
            db.query(AlertRecord)
            .filter(
                AlertRecord.user_id == user_id,
                AlertRecord.fingerprint == fingerprint,
                AlertRecord.status.in_(["open", "acknowledged"]),
                AlertRecord.created_at >= cooldown_cutoff,
            )
            .first()
        )

        if recent_existing:
            return None  # Cooldown active, skip duplicate alert

        alert = AlertRecord(
            api_id=api_id,
            user_id=user_id,
            title=title,
            description=description,
            severity=severity,
            status="open",
            source=source,
            fingerprint=fingerprint,
            created_at=now,
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        return alert

    def list_alerts(
        self,
        db: Session,
        user_id: str,
        status: Optional[str] = None,
        api_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[int, List[AlertRecord]]:
        query = db.query(AlertRecord).filter(AlertRecord.user_id == user_id)
        if status:
            query = query.filter(AlertRecord.status == status)
        if api_id:
            query = query.filter(AlertRecord.api_id == api_id)

        total = query.count()
        items = query.order_by(AlertRecord.created_at.desc()).offset(offset).limit(limit).all()
        return total, items

    def update_alert_status(
        self,
        db: Session,
        alert_id: str,
        user_id: str,
        new_status: str,
    ) -> AlertRecord:
        alert = db.query(AlertRecord).filter(AlertRecord.id == alert_id, AlertRecord.user_id == user_id).first()
        if not alert:
            raise AppException(status_code=404, code="NOT_FOUND", message="Alert not found")

        alert.status = new_status
        if new_status == "resolved":
            alert.resolved_at = datetime.now(timezone.utc)
        else:
            alert.resolved_at = None

        db.commit()
        db.refresh(alert)
        return alert
