# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# NO CHECKED-IN PROTOBUF GENCODE
# source: fraud_detection/fraud_detection.proto
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
    'fraud_detection/fraud_detection.proto'
)
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n%fraud_detection/fraud_detection.proto\x12\x0f\x66raud_detection\"5\n\x11\x46raudCheckRequest\x12\x10\n\x08order_id\x18\x01 \x01(\t\x12\x0e\n\x06\x61mount\x18\x02 \x01(\x01\"<\n\x12\x46raudCheckResponse\x12\x15\n\ris_fraudulent\x18\x01 \x01(\x08\x12\x0f\n\x07message\x18\x02 \x01(\t2g\n\x0e\x46raudDetection\x12U\n\nCheckFraud\x12\".fraud_detection.FraudCheckRequest\x1a#.fraud_detection.FraudCheckResponseb\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'fraud_detection.fraud_detection_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
  DESCRIPTOR._loaded_options = None
  _globals['_FRAUDCHECKREQUEST']._serialized_start=58
  _globals['_FRAUDCHECKREQUEST']._serialized_end=111
  _globals['_FRAUDCHECKRESPONSE']._serialized_start=113
  _globals['_FRAUDCHECKRESPONSE']._serialized_end=173
  _globals['_FRAUDDETECTION']._serialized_start=175
  _globals['_FRAUDDETECTION']._serialized_end=278
# @@protoc_insertion_point(module_scope)
