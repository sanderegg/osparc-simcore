# mypy: disable-error-code=truthy-function
from datetime import datetime
from typing import Annotated, Any

from common_library.basic_types import DEFAULT_FACTORY
from pydantic import ConfigDict, Field, HttpUrl
from pydantic.config import JsonDict

from .services_base import ServiceBaseDisplay
from .services_constants import LATEST_INTEGRATION_VERSION
from .services_enums import ServiceType
from .services_types import DynamicServiceKey, ServiceKey, ServiceVersion

assert DynamicServiceKey  # nosec
assert LATEST_INTEGRATION_VERSION  # nosec
assert ServiceKey  # nosec
assert ServiceType  # nosec
assert ServiceVersion  # nosec


class ServiceMetaDataEditable(ServiceBaseDisplay):
    # Overrides ServiceBaseDisplay fields to Optional for a partial update
    name: str | None  # type: ignore[assignment]
    thumbnail: str | None
    icon: HttpUrl | None
    description: str | None  # type: ignore[assignment]
    description_ui: bool = False
    version_display: str | None = None

    # Below fields only in the database ----
    deprecated: Annotated[
        datetime | None,
        Field(
            description="Owner can set the date to retire the service. Three possibilities:"
            "If None, the service is marked as `published`;"
            "If now<deprecated the service is marked as deprecated;"
            "If now>=deprecated, the service is retired",
        ),
    ] = None
    classifiers: list[str] | None
    quality: Annotated[
        dict[str, Any], Field(default_factory=dict, json_schema_extra={"default": {}})
    ] = DEFAULT_FACTORY

    @staticmethod
    def _update_json_schema_extra(schema: JsonDict) -> None:
        schema.update(
            {
                "example": {
                    "key": "simcore/services/dynamic/sim4life",
                    "version": "1.0.9",
                    "name": "sim4life",
                    "description": "s4l web",
                    "thumbnail": "https://thumbnailit.org/image",
                    "icon": "https://cdn-icons-png.flaticon.com/512/25/25231.png",
                    "quality": {
                        "enabled": True,
                        "tsr_target": {
                            f"r{n:02d}": {"level": 4, "references": ""}
                            for n in range(1, 11)
                        },
                        "annotations": {
                            "vandv": "",
                            "limitations": "",
                            "certificationLink": "",
                            "certificationStatus": "Uncertified",
                        },
                        "tsr_current": {
                            f"r{n:02d}": {"level": 0, "references": ""}
                            for n in range(1, 11)
                        },
                    },
                    "classifiers": [],
                }
            }
        )

    model_config = ConfigDict(json_schema_extra=_update_json_schema_extra)
