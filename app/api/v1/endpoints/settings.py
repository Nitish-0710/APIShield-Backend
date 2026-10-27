from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession, CsrfProtect
from app.schemas.ml import UserSettingsSchema, UserSettingsUpdate
from app.services.settings_service import SettingsService

router = APIRouter(prefix="/settings", tags=["Application Settings"])
settings_service = SettingsService()


@router.get(
    "",
    response_model=UserSettingsSchema,
    status_code=status.HTTP_200_OK,
    summary="Get user-specific application and monitoring settings",
)
def get_user_settings(
    db: DbSession,
    current_user: CurrentUser,
) -> UserSettingsSchema:
    settings_dict = settings_service.get_user_settings(db=db, user_id=current_user.id)
    return UserSettingsSchema.model_validate(settings_dict)


@router.put(
    "",
    response_model=UserSettingsSchema,
    status_code=status.HTTP_200_OK,
    summary="Update user-specific application and monitoring settings",
)
def update_user_settings(
    payload: UserSettingsUpdate,
    db: DbSession,
    current_user: CurrentUser,
    csrf: CsrfProtect,
) -> UserSettingsSchema:
    updated_dict = settings_service.update_user_settings(
        db=db,
        user_id=current_user.id,
        update_data=payload,
    )
    return UserSettingsSchema.model_validate(updated_dict)
