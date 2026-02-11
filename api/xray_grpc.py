"""Добавление/удаление пользователя в Xray через gRPC (Итерация 6)."""
import logging
import os
import sys

from bot.config import XRAY_INBOUND_TAG

logger = logging.getLogger(__name__)

# Путь к сгенерированным proto (common.*, app.*, proxy.*)
_GRPC_GEN = os.path.abspath(os.path.join(os.path.dirname(__file__), "xray_grpc_gen"))


def _ensure_grpc_gen_path():
    if _GRPC_GEN not in sys.path:
        sys.path.insert(0, _GRPC_GEN)


def add_user_to_xray(
    host: str,
    grpc_port: int,
    user_uuid: str,
    email: str,
    inbound_tag: str | None = None,
) -> bool:
    """
    Добавляет клиента во inbound Xray через gRPC (HandlerService.AlterInbound + AddUserOperation).

    :param host: хост сервера Xray
    :param grpc_port: порт gRPC API
    :param user_uuid: UUID клиента (VLESS)
    :param email: email/идентификатор клиента (например user_id)
    :param inbound_tag: тег inbound (по умолчанию из XRAY_INBOUND_TAG)
    :return: True при успехе
    :raises Exception: при ошибке gRPC
    """
    tag = inbound_tag or XRAY_INBOUND_TAG
    try:
        _add_user_grpc(host, grpc_port, user_uuid, email, tag)
        return True
    except ImportError as e:
        logger.warning(
            "Xray gRPC: сгенерированные proto не найдены. Заглушка: server=%s:%s uuid=%s email=%s tag=%s (%s)",
            host, grpc_port, user_uuid, email, tag, e,
        )
        return True
    except Exception as e:
        logger.exception("Xray AddUser failed: %s", e)
        raise


def remove_user_from_xray(
    host: str,
    grpc_port: int,
    email: str,
    inbound_tag: str | None = None,
) -> bool:
    """
    Удаляет клиента из inbound Xray через gRPC (HandlerService.AlterInbound + RemoveUserOperation).

    :param host: хост сервера Xray
    :param grpc_port: порт gRPC API
    :param email: email/идентификатор клиента (как при AddUser)
    :param inbound_tag: тег inbound (по умолчанию из XRAY_INBOUND_TAG)
    :return: True при успехе или если пользователь не найден (это нормально)
    :raises Exception: при критической ошибке gRPC
    """
    tag = inbound_tag or XRAY_INBOUND_TAG
    try:
        _remove_user_grpc(host, grpc_port, email, tag)
        return True
    except ImportError as e:
        logger.warning(
            "Xray gRPC: сгенерированные proto не найдены. Заглушка RemoveUser: server=%s:%s email=%s (%s)",
            host, grpc_port, email, e,
        )
        return True
    except Exception as e:
        # Если пользователь не найден - это нормально (уже удален или никогда не был добавлен)
        error_msg = str(e).lower()
        if "not found" in error_msg or "user" in error_msg and "not found" in error_msg:
            logger.debug("Xray RemoveUser: пользователь не найден (это нормально): server=%s:%s email=%s", host, grpc_port, email)
            return True
        # Для других ошибок логируем как предупреждение, но не пробрасываем исключение
        logger.warning("Xray RemoveUser failed (продолжаем): server=%s:%s email=%s error=%s", host, grpc_port, email, e)
        return True


def _add_user_grpc(
    host: str,
    grpc_port: int,
    user_uuid: str,
    email: str,
    inbound_tag: str,
) -> None:
    _ensure_grpc_gen_path()
    import grpc
    from app.proxyman.command import command_pb2, command_pb2_grpc
    from common.protocol import user_pb2
    from common.serial import typed_message_pb2
    from proxy.vless import account_pb2

    # VLESS Account: id=UUID, flow (xtls-rprx-vision или пусто), encryption=none
    vless_account = account_pb2.Account(
        id=user_uuid,
        flow="xtls-rprx-vision",
        encryption="none",
    )
    # Xray ожидает Type = FullName (без type.googleapis.com/), см. common/serial/typed_message.go
    account_typed = typed_message_pb2.TypedMessage(
        type="xray.proxy.vless.Account",
        value=vless_account.SerializeToString(),
    )
    user = user_pb2.User(level=0, email=email, account=account_typed)
    add_op = command_pb2.AddUserOperation(user=user)
    op_typed = typed_message_pb2.TypedMessage(
        type="xray.app.proxyman.command.AddUserOperation",
        value=add_op.SerializeToString(),
    )
    req = command_pb2.AlterInboundRequest(tag=inbound_tag, operation=op_typed)

    channel = grpc.insecure_channel(f"{host}:{grpc_port}")
    try:
        stub = command_pb2_grpc.HandlerServiceStub(channel)
        stub.AlterInbound(req)
    finally:
        channel.close()


def _remove_user_grpc(
    host: str,
    grpc_port: int,
    email: str,
    inbound_tag: str,
) -> None:
    _ensure_grpc_gen_path()
    import grpc
    from app.proxyman.command import command_pb2, command_pb2_grpc
    from common.serial import typed_message_pb2

    remove_op = command_pb2.RemoveUserOperation(email=email)
    op_typed = typed_message_pb2.TypedMessage(
        type="xray.app.proxyman.command.RemoveUserOperation",
        value=remove_op.SerializeToString(),
    )
    req = command_pb2.AlterInboundRequest(tag=inbound_tag, operation=op_typed)

    channel = grpc.insecure_channel(f"{host}:{grpc_port}")
    try:
        stub = command_pb2_grpc.HandlerServiceStub(channel)
        stub.AlterInbound(req)
    finally:
        channel.close()
