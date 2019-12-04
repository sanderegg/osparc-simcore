from enum import Enum

class SignalType(Enum):
    SIGNAL_USER_LOGOUT = 0
    SIGNAL_USER_CONNECT = 1
    SIGNAL_USER_DISCONNECT = 2
    SIGNAL_PROJECT_CONNECT = 3
    SIGNAL_PROJECT_DISCONNECT = 3
    SIGNAL_PROJECT_CLOSE = 4
