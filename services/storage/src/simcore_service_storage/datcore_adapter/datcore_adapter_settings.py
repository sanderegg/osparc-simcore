from functools import cached_property

from models_library.basic_types import PortInt, VersionTag
from pydantic import AnyHttpUrl, Field, TypeAdapter
from settings_library.base import BaseCustomSettings


class DatcoreAdapterSettings(BaseCustomSettings):
    DATCORE_ADAPTER_ENABLED: bool = True
    DATCORE_ADAPTER_HOST: str = "datcore-adapter"
    DATCORE_ADAPTER_PORT: PortInt = TypeAdapter(PortInt).validate_python(8000)
    DATCORE_ADAPTER_VTAG: VersionTag = Field(
        "v0", description="Datcore-adapter service API's version tag"
    )

    @cached_property
    def endpoint(self) -> str:
        endpoint = AnyHttpUrl.build(
            scheme="http",
            host=self.DATCORE_ADAPTER_HOST,
            port=self.DATCORE_ADAPTER_PORT,
            path=f"/{self.DATCORE_ADAPTER_VTAG}",
        )
        return f"{endpoint}"
