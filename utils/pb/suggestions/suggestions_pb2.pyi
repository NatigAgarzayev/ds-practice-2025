from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class SuggestionsRequest(_message.Message):
    __slots__ = ("user_id", "num_suggestions")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    NUM_SUGGESTIONS_FIELD_NUMBER: _ClassVar[int]
    user_id: str
    num_suggestions: int
    def __init__(self, user_id: _Optional[str] = ..., num_suggestions: _Optional[int] = ...) -> None: ...

class SuggestionsResponse(_message.Message):
    __slots__ = ("books",)
    BOOKS_FIELD_NUMBER: _ClassVar[int]
    books: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, books: _Optional[_Iterable[str]] = ...) -> None: ...

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
