# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# NO CHECKED-IN PROTOBUF GENCODE
# source: transaction_verification/transaction_verification.proto
# Protobuf Python Version: 5.29.0
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(
    _runtime_version.Domain.PUBLIC,
    5,
    29,
    0,
    '',
    'transaction_verification/transaction_verification.proto'
)
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n7transaction_verification/transaction_verification.proto\x12\x18transaction_verification\"m\n\x1eTransactionVerificationRequest\x12\x16\n\x0etransaction_id\x18\x01 \x01(\t\x12\x0f\n\x07user_id\x18\x02 \x01(\t\x12\r\n\x05items\x18\x03 \x03(\t\x12\x13\n\x0b\x63redit_card\x18\x04 \x01(\t\"D\n\x1fTransactionVerificationResponse\x12\x10\n\x08is_valid\x18\x01 \x01(\x08\x12\x0f\n\x07message\x18\x02 \x01(\t2\xa4\x01\n\x17TransactionVerification\x12\x88\x01\n\x11VerifyTransaction\x12\x38.transaction_verification.TransactionVerificationRequest\x1a\x39.transaction_verification.TransactionVerificationResponseb\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'transaction_verification.transaction_verification_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
  DESCRIPTOR._loaded_options = None
  _globals['_TRANSACTIONVERIFICATIONREQUEST']._serialized_start=85
  _globals['_TRANSACTIONVERIFICATIONREQUEST']._serialized_end=194
  _globals['_TRANSACTIONVERIFICATIONRESPONSE']._serialized_start=196
  _globals['_TRANSACTIONVERIFICATIONRESPONSE']._serialized_end=264
  _globals['_TRANSACTIONVERIFICATION']._serialized_start=267
  _globals['_TRANSACTIONVERIFICATION']._serialized_end=431
# @@protoc_insertion_point(module_scope)
