#!/bin/sh
# Регенерация Python из proto Xray (из корня проекта)
cd "$(dirname "$0")/.."
python -m grpc_tools.protoc -I proto_xray --python_out=api/xray_grpc_gen --grpc_python_out=api/xray_grpc_gen \
  proto_xray/common/serial/typed_message.proto \
  proto_xray/common/protocol/user.proto \
  proto_xray/proxy/vless/account.proto \
  proto_xray/app/proxyman/command/command.proto \
  proto_xray/app/stats/command/command.proto
