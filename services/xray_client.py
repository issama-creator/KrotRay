"""gRPC клиент для Xray Stats API и управления пользователями."""
import logging
import os
import sys

from bot.config import XRAY_INBOUND_TAG

logger = logging.getLogger(__name__)

# Путь к сгенерированным proto
_GRPC_GEN = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "api", "xray_grpc_gen"))


def _ensure_grpc_gen_path():
    if _GRPC_GEN not in sys.path:
        sys.path.insert(0, _GRPC_GEN)


def get_connections(host: str, grpc_port: int, user_email: str) -> int:
    """
    Получить количество активных подключений пользователя через Xray Stats API.
    Пробуем GetStatsOnlineIpList (число IP), иначе GetStatsOnline("user>>>email>>>online"),
    иначе GetStats("user>>>email>>>connections") — часто NOT_FOUND, тогда 0.

    :param host: хост сервера Xray
    :param grpc_port: порт gRPC API
    :param user_email: email пользователя (user_1, user_2, ...)
    :return: количество активных подключений (0 если ошибка или нет данных)
    """
    _ensure_grpc_gen_path()
    try:
        import grpc
        from app.stats.command import command_pb2, command_pb2_grpc

        name_with_prefix = f"user>>>{user_email}"
        channel = grpc.insecure_channel(f"{host}:{grpc_port}")
        try:
            stub = command_pb2_grpc.StatsServiceStub(channel)
            request = command_pb2.GetStatsRequest(name=name_with_prefix, reset=False)

            # 1) GetStatsOnlineIpList — число IP = число устройств. В Xray ключ = user>>>email>>>online
            if hasattr(stub, "GetStatsOnlineIpList"):
                name_online = f"{name_with_prefix}>>>online"
                for name in (name_online, name_with_prefix, user_email):
                    try:
                        req = command_pb2.GetStatsRequest(name=name, reset=False)
                        response = stub.GetStatsOnlineIpList(req)
                        ips = getattr(response, "ips", None) or {}
                        count = len(ips)
                        logger.debug("Stats API GetStatsOnlineIpList: name=%s connections(IPs)=%d", name, count)
                        return count
                    except grpc.RpcError as e:
                        if e.code() == grpc.StatusCode.NOT_FOUND:
                            continue
                        raise
                return 0

            # 2) GetStatsOnline("user>>>email>>>online") — один счётчик онлайн (если есть в стабе)
            if hasattr(stub, "GetStatsOnline"):
                try:
                    req_online = command_pb2.GetStatsRequest(name=f"{name_with_prefix}>>>online", reset=False)
                    resp = stub.GetStatsOnline(req_online)
                    if resp.stat and resp.stat.name:
                        logger.debug("Stats API GetStatsOnline: email=%s value=%s", user_email, resp.stat.value)
                        return int(resp.stat.value)
                except grpc.RpcError as e:
                    if e.code() == grpc.StatusCode.NOT_FOUND:
                        return 0
                    raise

            # 3) GetStats("user>>>email>>>connections") — в Xray часто нет такого счётчика
            try:
                req_conn = command_pb2.GetStatsRequest(name=f"{name_with_prefix}>>>connections", reset=False)
                response = stub.GetStats(req_conn)
                if response.stat and response.stat.name == req_conn.name:
                    return int(response.stat.value)
            except grpc.RpcError as e:
                if e.code() == grpc.StatusCode.NOT_FOUND:
                    logger.debug("Stats API: email=%s connections not found (0)", user_email)
                    return 0
                raise
            return 0
        finally:
            channel.close()
    except ImportError as e:
        logger.warning(
            "Xray Stats gRPC: proto не найдены. Заглушка: server=%s:%s email=%s (%s)",
            host, grpc_port, user_email, e,
        )
        return 0
    except Exception as e:
        logger.exception("Xray get_connections failed: server=%s:%s email=%s", host, grpc_port, user_email)
        return 0


def get_all_online_users(host: str, grpc_port: int) -> list[str]:
    """
    Список имён пользователей, у которых есть активные IP (для отладки формата name).
    """
    _ensure_grpc_gen_path()
    try:
        import grpc
        from app.stats.command import command_pb2, command_pb2_grpc
        channel = grpc.insecure_channel(f"{host}:{grpc_port}")
        try:
            stub = command_pb2_grpc.StatsServiceStub(channel)
            if hasattr(stub, "GetAllOnlineUsers"):
                resp = stub.GetAllOnlineUsers(command_pb2.GetAllOnlineUsersRequest())
                return list(getattr(resp, "users", []) or [])
        finally:
            channel.close()
    except Exception:
        pass
    return []


def disable_user(host: str, grpc_port: int, user_uuid: str, email: str, inbound_tag: str | None = None) -> bool:
    """
    Отключить пользователя в Xray (disable через AlterInbound).

    :param host: хост сервера Xray
    :param grpc_port: порт gRPC API
    :param user_uuid: UUID пользователя
    :param email: email/идентификатор пользователя
    :param inbound_tag: тег inbound (по умолчанию из XRAY_INBOUND_TAG)
    :return: True при успехе
    :raises Exception: при ошибке gRPC
    """
    tag = inbound_tag or XRAY_INBOUND_TAG
    _ensure_grpc_gen_path()
    try:
        import grpc
        from app.proxyman.command import command_pb2, command_pb2_grpc
        from common.protocol import user_pb2
        from common.serial import typed_message_pb2
        from proxy.vless import account_pb2

        # VLESS Account с тем же UUID
        vless_account = account_pb2.Account(
            id=user_uuid,
            flow="xtls-rprx-vision",
            encryption="none",
        )
        account_typed = typed_message_pb2.TypedMessage(
            type="xray.proxy.vless.Account",
            value=vless_account.SerializeToString(),
        )
        user = user_pb2.User(level=0, email=email, account=account_typed)

        # RemoveUserOperation для отключения
        remove_op = command_pb2.RemoveUserOperation(email=email)
        op_typed = typed_message_pb2.TypedMessage(
            type="xray.app.proxyman.command.RemoveUserOperation",
            value=remove_op.SerializeToString(),
        )
        req = command_pb2.AlterInboundRequest(tag=tag, operation=op_typed)

        channel = grpc.insecure_channel(f"{host}:{grpc_port}")
        try:
            stub = command_pb2_grpc.HandlerServiceStub(channel)
            stub.AlterInbound(req)
            logger.info("Xray user disabled: server=%s:%s uuid=%s email=%s", host, grpc_port, user_uuid, email)
            return True
        finally:
            channel.close()
    except ImportError as e:
        logger.warning(
            "Xray gRPC: proto не найдены. Заглушка disable: server=%s:%s uuid=%s email=%s (%s)",
            host, grpc_port, user_uuid, email, e,
        )
        return True
    except Exception as e:
        logger.exception("Xray DisableUser failed: server=%s:%s uuid=%s email=%s", host, grpc_port, user_uuid, email)
        raise


def enable_user(host: str, grpc_port: int, user_uuid: str, email: str, inbound_tag: str | None = None) -> bool:
    """
    Включить пользователя в Xray (add через AlterInbound).

    :param host: хост сервера Xray
    :param grpc_port: порт gRPC API
    :param user_uuid: UUID пользователя
    :param email: email/идентификатор пользователя
    :param inbound_tag: тег inbound (по умолчанию из XRAY_INBOUND_TAG)
    :return: True при успехе
    :raises Exception: при ошибке gRPC
    """
    tag = inbound_tag or XRAY_INBOUND_TAG
    _ensure_grpc_gen_path()
    try:
        import grpc
        from app.proxyman.command import command_pb2, command_pb2_grpc
        from common.protocol import user_pb2
        from common.serial import typed_message_pb2
        from proxy.vless import account_pb2

        # VLESS Account: id=UUID, flow (xtls-rprx-vision), encryption=none
        vless_account = account_pb2.Account(
            id=user_uuid,
            flow="xtls-rprx-vision",
            encryption="none",
        )
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
        req = command_pb2.AlterInboundRequest(tag=tag, operation=op_typed)

        channel = grpc.insecure_channel(f"{host}:{grpc_port}")
        try:
            stub = command_pb2_grpc.HandlerServiceStub(channel)
            stub.AlterInbound(req)
            logger.info("Xray user enabled: server=%s:%s uuid=%s email=%s", host, grpc_port, user_uuid, email)
            return True
        finally:
            channel.close()
    except ImportError as e:
        logger.warning(
            "Xray gRPC: proto не найдены. Заглушка enable: server=%s:%s uuid=%s email=%s (%s)",
            host, grpc_port, user_uuid, email, e,
        )
        return True
    except Exception as e:
        logger.exception("Xray EnableUser failed: server=%s:%s uuid=%s email=%s", host, grpc_port, user_uuid, email)
        raise
