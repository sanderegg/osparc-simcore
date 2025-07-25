"""Project document versioning utilities.

This module provides utilities for managing project document versions using Redis.
The versioning system ensures that all users working on a project are synchronized
with the latest changes through atomic version incrementing.
"""

from typing import Final

from models_library.projects import ProjectID

from ._client import RedisClientSDK

# Redis key patterns
PROJECT_DOCUMENT_VERSION_KEY: Final[str] = "projects:{}:version"
PROJECT_DB_UPDATE_REDIS_LOCK_KEY: Final[str] = "project_db_update:{}"


async def increment_and_return_project_document_version(
    redis_client: RedisClientSDK, project_uuid: ProjectID
) -> int:
    """
    Atomically increments and returns the project document version using Redis.
    Returns the incremented version number.

    This function ensures thread-safe version incrementing by using Redis INCR command
    which is atomic. The version starts at 1 for the first call.

    Args:
        redis_client: The Redis client SDK instance
        project_uuid: The project UUID to get/increment version for

    Returns:
        The new (incremented) version number
    """
    version_key = PROJECT_DOCUMENT_VERSION_KEY.format(project_uuid)
    # If key doesn't exist, it's created with value 0 and then incremented to 1
    output = await redis_client.redis.incr(version_key)
    return int(output)
