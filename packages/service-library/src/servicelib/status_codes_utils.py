""" Usage

    - on aiohttp services
        from servicelib.aiohttp import status
        from servicelib.status_codes_utils import is_success

        assert is_success(status.HTTP_200_OK)


    - on fastapi services

        from fastapi import status
        from servicelib.status_codes_utils import is_success

        assert is_success(status.HTTP_200_OK)

    NOTE: https://github.com/encode/httpx/blob/master/httpx/_status_codes.py
"""

import types
from collections.abc import Callable
from http import HTTPStatus
from typing import Final

_INVALID_STATUS_CODE_MSG = "INVALID_STATUS_CODE"


def get_code_display_name(status_code: int) -> str:
    """
    Returns display name given a status code, e.g.

        get_display_name(200) == "HTTP_200_OK"
        get_display_name(status.HTTP_200_OK) == "HTTP_200_OK"
    """
    try:
        code = HTTPStatus(status_code)
        return f"HTTP_{status_code}_{code.name}"
    except ValueError:
        if status_code == 306:  # noqa: PLR2004
            # NOTE: HttpStatus does not include 306
            return "HTTP_306_RESERVED"
        return _INVALID_STATUS_CODE_MSG


_CODE_DESCRIPTION_TEMPLATE: Final[
    str
] = "{description}. See https://developer.mozilla.org/en-US/docs/Web/HTTP/Status{url_suffix}"


def get_code_description(status_code: int) -> str:
    try:
        description = HTTPStatus(status_code).description
    except ValueError:
        description = "Unused"

    match status_code:
        case 305:
            url_suffix = "#305_use_proxy"
        case 306:
            url_suffix = "#306_unused"
        case _:
            url_suffix = f"/{status_code}"

    return _CODE_DESCRIPTION_TEMPLATE.format(
        description=description, url_suffix=url_suffix
    )


def is_1xx_informational(status_code: int) -> bool:
    """
    Returns `True` for 1xx status codes, `False` otherwise.
    """
    return 100 <= status_code <= 199  # noqa: PLR2004


def is_2xx_success(status_code: int) -> bool:
    """
    Returns `True` for 2xx status codes, `False` otherwise.
    """
    return 200 <= status_code <= 299  # noqa: PLR2004


def is_3xx_redirect(status_code: int) -> bool:
    """
    Returns `True` for 3xx status codes, `False` otherwise.
    """
    return 300 <= status_code <= 399  # noqa: PLR2004


def is_4xx_client_error(status_code: int) -> bool:
    """
    Returns `True` for 4xx status codes, `False` otherwise.
    """
    return 400 <= status_code <= 499  # noqa: PLR2004


def is_5xx_server_error(status_code: int) -> bool:
    """
    Returns `True` for 5xx status codes, `False` otherwise.
    """
    return 500 <= status_code <= 599  # noqa: PLR2004


def is_error(status_code: int) -> bool:
    """
    Returns `True` for 4xx or 5xx status codes, `False` otherwise.
    """
    return 400 <= status_code <= 599  # noqa: PLR2004


def get_http_status_codes(
    status: types.ModuleType, predicate: Callable[[int], bool] | None = None
) -> list[int]:
    # In the spirit of https://docs.python.org/3/library/inspect.html#inspect.getmembers
    iter_all = (
        getattr(status, code) for code in status.__all__ if code.startswith("HTTP_")
    )
    if predicate is None:
        return list(iter_all)
    return [code for code in iter_all if predicate(code)]
