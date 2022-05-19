from pydantic.errors import PydanticErrorMixin


class FileMetaDataNotFoundError(PydanticErrorMixin, RuntimeError):
    code = "filemetadata.not_found_error"
    msg_template: str = "The file meta data for {file_uuid} was not found"
