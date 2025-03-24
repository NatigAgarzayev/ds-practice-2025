from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class CachedOrderRequest(_message.Message):
    __slots__ = ("order_id", "payload", "clock")
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    CLOCK_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    payload: str
    clock: str
    def __init__(self, order_id: _Optional[str] = ..., payload: _Optional[str] = ..., clock: _Optional[str] = ...) -> None: ...

class OrderProcessRequest(_message.Message):
    __slots__ = ("order_id",)
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    def __init__(self, order_id: _Optional[str] = ...) -> None: ...

class FraudCheckResponse(_message.Message):
    __slots__ = ("is_fraudulent", "message")
    IS_FRAUDULENT_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    is_fraudulent: bool
    message: str
    def __init__(self, is_fraudulent: bool = ..., message: _Optional[str] = ...) -> None: ...

class CacheAck(_message.Message):
    __slots__ = ("message",)
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    message: str
    def __init__(self, message: _Optional[str] = ...) -> None: ...

class EventRequest(_message.Message):
    __slots__ = ("order_id", "event", "clock")
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    EVENT_FIELD_NUMBER: _ClassVar[int]
    CLOCK_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    event: str
    clock: str
    def __init__(self, order_id: _Optional[str] = ..., event: _Optional[str] = ..., clock: _Optional[str] = ...) -> None: ...

class EventResponse(_message.Message):
    __slots__ = ("success", "message", "clock")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    CLOCK_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    clock: str
    def __init__(self, success: bool = ..., message: _Optional[str] = ..., clock: _Optional[str] = ...) -> None: ...

class ClearRequest(_message.Message):
    __slots__ = ("order_id", "final_clock")
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    FINAL_CLOCK_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    final_clock: str
    def __init__(self, order_id: _Optional[str] = ..., final_clock: _Optional[str] = ...) -> None: ...

class ClearResponse(_message.Message):
    __slots__ = ("cleared", "service", "error")
    CLEARED_FIELD_NUMBER: _ClassVar[int]
    SERVICE_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    cleared: bool
    service: str
    error: str
    def __init__(self, cleared: bool = ..., service: _Optional[str] = ..., error: _Optional[str] = ...) -> None: ...
