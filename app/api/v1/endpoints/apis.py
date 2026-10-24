from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import AppException, CurrentUser, DbSession, verify_csrf
from app.schemas.api import (
    ApiEndpointInput,
    ApiEndpointResponse,
    ApiEndpointUpdate,
)
from app.schemas.testing import (
    TestRequestSchema,
    TestResultResponse,
)
from app.services.api_service import ApiService, to_api_response
from app.services.test_service import TestService

router = APIRouter(prefix="/apis", tags=["APIs"])


@router.get(
    "",
    response_model=List[ApiEndpointResponse],
    status_code=status.HTTP_200_OK,
    summary="List saved APIs owned by authenticated user",
)
def list_apis(
    db: DbSession,
    current_user: CurrentUser,
) -> List[ApiEndpointResponse]:
    """Retrieve all API endpoints owned by the currently authenticated user."""
    apis = ApiService.list_apis(db, current_user)
    return [to_api_response(api) for api in apis]


@router.post(
    "",
    response_model=ApiEndpointResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new saved API endpoint",
    dependencies=[Depends(verify_csrf)],
)
def create_api(
    data: ApiEndpointInput,
    db: DbSession,
    current_user: CurrentUser,
) -> ApiEndpointResponse:
    """Create a new API endpoint record with encrypted credential storage."""
    api = ApiService.create_api(db, current_user, data)
    return to_api_response(api)


# --- AD-HOC TESTING (Declared before dynamic /{api_id} routes to prevent path conflict) ---

@router.post(
    "/adhoc/test",
    response_model=TestResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute an ad-hoc test request with strict SSRF enforcement",
    dependencies=[Depends(verify_csrf)],
)
def test_adhoc_endpoint(
    data: TestRequestSchema,
    db: DbSession,
    current_user: CurrentUser,
) -> TestResultResponse:
    """Execute an ad-hoc test request, evaluate response assertions, enforce SSRF, and persist history."""
    return TestService.run_adhoc_test(db, current_user, data)


# --- DYNAMIC /{api_id} ROUTES ---

@router.get(
    "/{api_id}",
    response_model=ApiEndpointResponse,
    status_code=status.HTTP_200_OK,
    summary="Get saved API endpoint details by ID",
)
def get_api(
    api_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> ApiEndpointResponse:
    """Retrieve details for a specific API endpoint owned by the authenticated user."""
    api = ApiService.get_api(db, current_user, api_id)
    if not api:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="NOT_FOUND",
            message="API endpoint not found.",
        )
    return to_api_response(api)


@router.patch(
    "/{api_id}",
    response_model=ApiEndpointResponse,
    status_code=status.HTTP_200_OK,
    summary="Update an existing saved API endpoint",
    dependencies=[Depends(verify_csrf)],
)
def update_api(
    api_id: str,
    data: ApiEndpointUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> ApiEndpointResponse:
    """Update configuration and credentials for an API endpoint owned by the authenticated user."""
    api = ApiService.update_api(db, current_user, api_id, data)
    if not api:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="NOT_FOUND",
            message="API endpoint not found.",
        )
    return to_api_response(api)


@router.delete(
    "/{api_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a saved API endpoint",
    dependencies=[Depends(verify_csrf)],
)
def delete_api(
    api_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> Response:
    """Delete a saved API endpoint record owned by the authenticated user."""
    success = ApiService.delete_api(db, current_user, api_id)
    if not success:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="NOT_FOUND",
            message="API endpoint not found.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{api_id}/test",
    response_model=TestResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute a test on a saved API endpoint",
    dependencies=[Depends(verify_csrf)],
)
def test_saved_api(
    api_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> TestResultResponse:
    """Execute a test on a saved API endpoint, decrypting credentials and applying SSRF protections."""
    result = TestService.run_saved_api_test(db, current_user, api_id)
    if not result:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="NOT_FOUND",
            message="API endpoint not found.",
        )
    return result


@router.get(
    "/{api_id}/history",
    response_model=List[TestResultResponse],
    status_code=status.HTTP_200_OK,
    summary="Get persistent test execution history for a saved API",
)
def get_api_history(
    api_id: str,
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=100),
) -> List[TestResultResponse]:
    """Retrieve recent test history for an API endpoint owned by the authenticated user."""
    history = TestService.get_test_history(db, current_user, api_id, limit=limit)
    if history is None:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="NOT_FOUND",
            message="API endpoint not found.",
        )
    return history
