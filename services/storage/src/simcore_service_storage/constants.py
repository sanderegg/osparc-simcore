from servicelib.aiohttp import application_keys

from . import _meta

RETRY_WAIT_SECS = 2
RETRY_COUNT = 20
CONNECT_TIMEOUT_SECS = 30
MAX_CHUNK_SIZE = 1024
MINUTE = 60

## VERSION-----------------------------
service_version = _meta.version

## CONFIGURATION FILES------------------
DEFAULT_CONFIG = "docker-prod-config.yaml"


APP_CONFIG_KEY = application_keys.APP_CONFIG_KEY  # app-storage-key for config object
RSC_CONFIG_DIR_KEY = "data"  # resource folder

# DSM locations
SIMCORE_S3_ID = 0
SIMCORE_S3_STR = "simcore.s3"

DATCORE_ID = 1
DATCORE_STR = "datcore"

LOCATION_ID_TO_TAG_MAP = {0: SIMCORE_S3_STR, 1: DATCORE_STR}
UNDEFINED_LOCATION_TAG: str = "undefined"

# NOTE: SAFE S3 characters are found here [https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-keys.html]
# the % character was added since we need to url encode some of them
_SAFE_S3_FILE_NAME_RE = r"[\w!\-_\.\*\'\(\)\%]"
S3_FILE_ID_RE = rf"^({_SAFE_S3_FILE_NAME_RE}+?)\/({_SAFE_S3_FILE_NAME_RE}+?)\/({_SAFE_S3_FILE_NAME_RE}+?)$"
S3_BUCKET_NAME_RE = r"(?!(^xn--|-s3alias$))^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$"
# file IDs are either of type uuid/uuid/file_name.ext or api/uuid/file_name.ext
_UUID_RE = r"[a-fA-F\d]{8}(?:\-[a-fA-F\d]{4}){3}\-[a-fA-F\d]{12}"
FILE_ID_RE = r"^(api|(.+))/((.+))/(.+)$"


# REST API ----------------------------
API_MAJOR_VERSION = service_version.major  # NOTE: syncs with service key
API_VERSION_TAG = "v{:.0f}".format(API_MAJOR_VERSION)

APP_OPENAPI_SPECS_KEY = (
    application_keys.APP_OPENAPI_SPECS_KEY
)  # app-storage-key for openapi specs object


# DATABASE ----------------------------
APP_DB_ENGINE_KEY = f"{__name__}.db_engine"


# DATA STORAGE MANAGER ----------------------------------
APP_DSM_THREADPOOL = f"{__name__}.dsm_threadpool"
APP_DSM_KEY = f"{__name__}.DSM"
APP_S3_KEY = f"{__name__}.S3_CLIENT"
