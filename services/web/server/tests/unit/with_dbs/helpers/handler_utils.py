from collections import namedtuple
from typing import List, Tuple

from aiohttp import web

from simcore_service_webserver.security_roles import UserRole

ExpectedResponse = namedtuple(
    "ExpectedResponse", ["ok", "created", "no_content", "not_found"]
)



def standard_role_response() -> Tuple[str, List[Tuple[UserRole, ExpectedResponse]]]:
    return (
        "role,expected",
        [
            (
                UserRole.ANONYMOUS,
                ExpectedResponse(
                    web.HTTPUnauthorized,
                    web.HTTPUnauthorized,
                    web.HTTPUnauthorized,
                    web.HTTPUnauthorized,
                ),
            ),
            (
                UserRole.GUEST,
                ExpectedResponse(
                    web.HTTPForbidden,
                    web.HTTPForbidden,
                    web.HTTPForbidden,
                    web.HTTPForbidden,
                ),
            ),
            (
                UserRole.USER,
                ExpectedResponse(
                    web.HTTPOk, web.HTTPCreated, web.HTTPNoContent, web.HTTPNotFound,
                ),
            ),
            (
                UserRole.TESTER,
                ExpectedResponse(
                    web.HTTPOk, web.HTTPCreated, web.HTTPNoContent, web.HTTPNotFound,
                ),
            ),
        ],
    )
