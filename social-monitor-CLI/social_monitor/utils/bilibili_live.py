"""B站直播弹幕 WebSocket 协议工具"""

from __future__ import annotations

import json
import struct
import zlib
from typing import Any, Dict, List, Tuple

LIVE_WS_URL = "wss://broadcastlv.chat.bilibili.com/sub"


HEADER_FORMAT = ">IHHHI"
HEADER_SIZE = 16


def pack_packet(body: bytes, action: int = 5) -> bytes:
    """封装直播弹幕二进制包"""
    total_len = len(body) + HEADER_SIZE
    header = struct.pack(HEADER_FORMAT, total_len, HEADER_SIZE, 1, action, 1)
    padding = b"\x00\x00"
    return header + padding + body


def unpack_packets(data: bytes) -> List[Tuple[int, int, bytes]]:
    """解析直播弹幕二进制包，返回 (version, action, body) 列表"""
    packets: List[Tuple[int, int, bytes]] = []
    offset = 0
    while offset + 14 <= len(data):
        total_len, header_len, version, action, _param = struct.unpack_from(
            HEADER_FORMAT, data, offset
        )
        if total_len < header_len or offset + total_len > len(data):
            break
        body = data[offset + header_len : offset + total_len]
        packets.append((version, action, body))
        offset += total_len
    return packets


def decode_body(version: int, body: bytes) -> bytes:
    """解压直播弹幕包体（支持 zlib / brotli）"""
    if version == 2:
        return zlib.decompress(body)
    if version == 3:
        try:
            import brotli
        except ImportError:
            raise RuntimeError("直播弹幕需要 brotli 解压，请安装: pip install brotli") from None
        return brotli.decompress(body)
    return body


def build_auth_packet(room_id: int) -> bytes:
    """构建直播间鉴权包"""
    payload = json.dumps(
        {
            "uid": 0,
            "roomid": room_id,
            "protover": 2,
            "platform": "web",
            "type": 2,
            "key": "",
        },
        ensure_ascii=False,
    ).encode("utf-8")
    return pack_packet(payload, action=7)


def build_heartbeat_packet() -> bytes:
    """构建心跳包"""
    return pack_packet(b"[object Object]", action=2)


def _iter_json_payloads(version: int, action: int, body: bytes):
    """展开直播包体为 JSON payload 列表"""
    if action == 3:
        return
    if version in (2, 3):
        try:
            decoded = decode_body(version, body)
        except Exception:
            return
        for _ver, inner_action, inner_body in unpack_packets(decoded):
            if inner_action == 5:
                yield inner_body
        return
    if action == 5:
        yield body


def parse_live_messages(raw: bytes) -> List[Dict[str, Any]]:
    """从 WebSocket 原始数据解析弹幕消息"""
    messages: List[Dict[str, Any]] = []
    for version, action, body in unpack_packets(raw):
        for inner_body in _iter_json_payloads(version, action, body):
            try:
                payload = json.loads(inner_body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            cmd = payload.get("cmd", "")
            if cmd == "DANMU_MSG":
                info = payload.get("info") or []
                if len(info) < 3:
                    continue
                user_info = info[2] if isinstance(info[2], list) else []
                messages.append(
                    {
                        "content": str(info[1]),
                        "user": user_info[1] if len(user_info) > 1 else "",
                        "uid": user_info[4] if len(user_info) > 4 else 0,
                        "room_id": payload.get("roomid", 0),
                        "platform": "bilibili_live",
                    }
                )
            elif cmd == "INTERACT_WORD":
                data = payload.get("data") or {}
                messages.append(
                    {
                        "content": f"[{data.get('msg_type', 'enter')}]",
                        "user": data.get("uname", ""),
                        "uid": data.get("uid", 0),
                        "room_id": data.get("roomid", 0),
                        "platform": "bilibili_live",
                    }
                )
    return messages
