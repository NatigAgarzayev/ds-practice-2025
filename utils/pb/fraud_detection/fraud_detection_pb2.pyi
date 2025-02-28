from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class FraudCheckRequest(_message.Message):
    __slots__ = ("order_id", "amount")
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    amount: float
    def __init__(self, order_id: _Optional[str] = ..., amount: _Optional[float] = ...) -> None: ...

class FraudCheckResponse(_message.Message):
    __slots__ = ("is_fraudulent", "message")
    IS_FRAUDULENT_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    is_fraudulent: bool
    message: str
    def __init__(self, is_fraudulent: bool = ..., message: _Optional[str] = ...) -> None: ...
