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
