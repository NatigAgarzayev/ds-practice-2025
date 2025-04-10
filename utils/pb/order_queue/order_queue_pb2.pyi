from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class OrderRequest(_message.Message):
    __slots__ = ("order_id", "num_items", "is_premium", "shipping_method")
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    NUM_ITEMS_FIELD_NUMBER: _ClassVar[int]
    IS_PREMIUM_FIELD_NUMBER: _ClassVar[int]
    SHIPPING_METHOD_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    num_items: int
    is_premium: bool
    shipping_method: str
    def __init__(self, order_id: _Optional[str] = ..., num_items: _Optional[int] = ..., is_premium: bool = ..., shipping_method: _Optional[str] = ...) -> None: ...

class QueueAck(_message.Message):
    __slots__ = ("success", "message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    def __init__(self, success: bool = ..., message: _Optional[str] = ...) -> None: ...

class Empty(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class OrderResponse(_message.Message):
    __slots__ = ("order_id", "has_order")
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    HAS_ORDER_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    has_order: bool
    def __init__(self, order_id: _Optional[str] = ..., has_order: bool = ...) -> None: ...
