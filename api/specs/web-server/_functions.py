# pylint: disable=protected-access
# pylint: disable=redefined-outer-name
# pylint: disable=too-many-arguments
# pylint: disable=unused-argument
# pylint: disable=unused-variable


from typing import Annotated

from fastapi import APIRouter, Depends, status
from models_library.api_schemas_webserver.functions import (
    FunctionToRegister,
    RegisteredFunctionGet,
)
from models_library.generics import Envelope
from simcore_service_webserver._meta import API_VTAG
from simcore_service_webserver.functions._controller._functions_rest_schemas import (
    FunctionPathParams,
)

router = APIRouter(
    prefix=f"/{API_VTAG}",
    tags=[
        "functions",
    ],
)


@router.post(
    "/functions",
    response_model=Envelope[RegisteredFunctionGet],
)
async def register_function(
    _body: FunctionToRegister,
) -> Envelope[RegisteredFunctionGet]: ...


@router.get(
    "/functions/{function_id}",
    response_model=Envelope[RegisteredFunctionGet],
)
async def get_function(
    _path: Annotated[FunctionPathParams, Depends()],
): ...


@router.delete(
    "/functions/{function_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_function(
    _path: Annotated[FunctionPathParams, Depends()],
): ...
