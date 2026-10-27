from datetime import datetime, timezone
from typing import Any, Dict
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.ml import SettingRecord
from app.schemas.ml import UserSettingsSchema, UserSettingsUpdate


class SettingsService:
    def get_user_settings(self, db: Session, user_id: str) -> Dict[str, Any]:
        record = db.query(SettingRecord).filter(SettingRecord.user_id == user_id).first()
        if not record:
            default_settings = UserSettingsSchema().model_dump()
            record = SettingRecord(
                user_id=user_id,
                settings=default_settings,
                updated_at=datetime.now(timezone.utc),
            )
            db.add(record)
            db.commit()
            db.refresh(record)
        return dict(record.settings)

    def update_user_settings(
        self,
        db: Session,
        user_id: str,
        update_data: UserSettingsUpdate,
    ) -> Dict[str, Any]:
        record = db.query(SettingRecord).filter(SettingRecord.user_id == user_id).first()
        base_dict = dict(record.settings) if record else UserSettingsSchema().model_dump()

        updates = update_data.model_dump(exclude_unset=True)
        base_dict.update(updates)

        validated = UserSettingsSchema(**base_dict).model_dump()

        if not record:
            record = SettingRecord(
                user_id=user_id,
                settings=validated,
                updated_at=datetime.now(timezone.utc),
            )
            db.add(record)
        else:
            record.settings = dict(validated)
            flag_modified(record, "settings")
            record.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(record)
        return dict(record.settings)
