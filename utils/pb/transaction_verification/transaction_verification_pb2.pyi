from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Item(_message.Message):
    __slots__ = ("book_id", "quantity")
    BOOK_ID_FIELD_NUMBER: _ClassVar[int]
    QUANTITY_FIELD_NUMBER: _ClassVar[int]
    book_id: str
    quantity: int
    def __init__(self, book_id: _Optional[str] = ..., quantity: _Optional[int] = ...) -> None: ...

class TransactionVerificationRequest(_message.Message):
    __slots__ = ("transaction_id", "user_id", "items", "credit_card")
    TRANSACTION_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    ITEMS_FIELD_NUMBER: _ClassVar[int]
    CREDIT_CARD_FIELD_NUMBER: _ClassVar[int]
    transaction_id: str
    user_id: str
    items: _containers.RepeatedCompositeFieldContainer[Item]
    credit_card: str
    def __init__(self, transaction_id: _Optional[str] = ..., user_id: _Optional[str] = ..., items: _Optional[_Iterable[_Union[Item, _Mapping]]] = ..., credit_card: _Optional[str] = ...) -> None: ...

class TransactionVerificationResponse(_message.Message):
    __slots__ = ("is_valid", "message")
    IS_VALID_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    is_valid: bool
    message: str
    def __init__(self, is_valid: bool = ..., message: _Optional[str] = ...) -> None: ...
