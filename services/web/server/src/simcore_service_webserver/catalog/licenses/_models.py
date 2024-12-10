import logging

from models_library.basic_types import IDStr
from models_library.licensed_items import LicensedItemID
from models_library.rest_base import RequestParameters, StrictRequestParameters
from models_library.rest_ordering import (
    OrderBy,
    OrderDirection,
    create_ordering_query_model_class,
)
from models_library.rest_pagination import PageQueryParameters
from models_library.users import UserID
from models_library.wallets import WalletID
from pydantic import BaseModel, ConfigDict, Field
from servicelib.request_keys import RQT_USERID_KEY

from ..._constants import RQ_PRODUCT_KEY

_logger = logging.getLogger(__name__)


class LicensedItemsRequestContext(RequestParameters):
    user_id: UserID = Field(..., alias=RQT_USERID_KEY)  # type: ignore[literal-required]
    product_name: str = Field(..., alias=RQ_PRODUCT_KEY)  # type: ignore[literal-required]


class LicensedItemsPathParams(StrictRequestParameters):
    licensed_item_id: LicensedItemID


_LicensedItemsListOrderQueryParams: type[
    RequestParameters
] = create_ordering_query_model_class(
    ordering_fields={
        "modified_at",
        "name",
    },
    default=OrderBy(field=IDStr("modified_at"), direction=OrderDirection.DESC),
    ordering_fields_api_to_column_map={"modified_at": "modified"},
)


class LicensedItemsListQueryParams(
    PageQueryParameters,
    _LicensedItemsListOrderQueryParams,  # type: ignore[misc, valid-type]
):
    ...


class LicensedItemsBodyParams(BaseModel):
    wallet_id: WalletID
    num_of_seeds: int

    model_config = ConfigDict(extra="forbid")