# -*- coding: utf-8 -*-
"""Pure outbound delivery classification used at the platform boundary."""
from __future__ import annotations

import re
from typing import Any

from .helpers import _single_line

def looks_like_internal_provider_error_text(text: Any) -> bool:
    cleaned = _single_line(text, 1000).lower()
    if not cleaned:
        return False
    normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff_]+", " ", cleaned).strip()
    compact = re.sub(r"[^a-z0-9\u4e00-\u9fff_]+", "", cleaned)
    direct_markers = (
        "all chat models failed",
        "all llm providers failed",
        "prompt could not be submitted",
        "prompt was not submitted",
        "try rephrasing the prompt",
        "generative ai prohibited use policy",
        "prompt contains sensitive words",
        "badrequesterror",
        "api connection error",
        "apiconnectionerror",
        "api status error",
        "apistatuserror",
        "authenticationerror",
        "permissiondeniederror",
        "ratelimiterror",
        "notfounderror",
        "internalservererror",
        "provider api error",
        "unable to submit request",
        "invalid_request",
        "invalid request error",
        "主动消息专用模式下",
        "普通被动回复不可使用 private companion 工具",
        "主动渲染阶段不可使用 private companion 工具",
        "has sent the result directly to the user",
        "error code: 400",
        "error code 400",
        "400 bad request",
        "模型调用失败",
        "工具调用失败",
        "函数工具调用失败",
        "api 调用失败",
        "api调用失败",
        "provider 调用失败",
        "provider调用失败",
        "没有返回值，或者已将结果直接发送给用户",
        "没有返回值,或者已将结果直接发送给用户",
    )
    compact_markers = (
        "allchatmodelsfailed",
        "allllmprovidersfailed",
        "promptcouldnotbesubmitted",
        "promptwasnotsubmitted",
        "tryrephrasingtheprompt",
        "generativeaiprohibitedusepolicy",
        "promptcontainssensitivewords",
        "badrequesterror",
        "apiconnectionerror",
        "apistatuserror",
        "authenticationerror",
        "permissiondeniederror",
        "ratelimiterror",
        "notfounderror",
        "internalservererror",
        "providerapierror",
        "unabletosubmitrequest",
        "invalid_request",
        "invalidrequesterror",
        "主动消息专用模式下",
        "普通被动回复不可使用privatecompanion工具",
        "主动渲染阶段不可使用privatecompanion工具",
        "hassenttheresultdirectlytotheuser",
        "errorcode400",
        "400badrequest",
        "模型调用失败",
        "工具调用失败",
        "函数工具调用失败",
        "api调用失败",
        "provider调用失败",
        "没有返回值或者已将结果直接发送给用户",
    )
    if any(marker in cleaned or marker in normalized for marker in direct_markers):
        return True
    if any(marker in compact for marker in compact_markers):
        return True
    provider_error_context = any(
        token in compact
        for token in (
            "providerapierror",
            "errorcode",
            "statuscode",
            "badrequest",
            "invalidrequest",
            "requestfailed",
            "请求失败",
            "调用失败",
            "模型调用失败",
            "工具调用失败",
        )
    )
    if "errorcode" in compact and any(
        token in compact
        for token in (
            "badrequest",
            "invalidrequest",
            "provider",
            "apierror",
            "functiondeclaration",
        )
    ):
        return True
    if "functiondeclaration" in compact and provider_error_context and any(
        token in compact for token in ("schema", "properties", "parameters", "tool", "tools", "badrequest", "invalidrequest")
    ):
        return True
    if any(token in compact for token in ("schemadidntspecify", "toolschema", "image_url", "invalidparameter")) and provider_error_context:
        return True
    if "aisearch" in cleaned and any(
        marker in cleaned
        for marker in (
            "failed",
            "badrequest",
            "invalid_request",
            "unable to submit",
            "provider api",
        )
    ):
        return True
    return False


def is_onebot_event_checker_send_rejection(error: Any) -> bool:
    """Identify the NTQQ sendMsg rejection shared by every aiocqhttp send route."""
    text = str(error or "").strip().lower()
    compact = re.sub(r"\s+", "", text)
    has_retcode = any(
        token in compact
        for token in ("retcode=1200", "retcode:1200", "'retcode':1200", '\"retcode\":1200')
    )
    return bool(
        has_retcode
        and "eventcheckerfailed" in compact
        and ("sendmsg" in compact or "nodeikernelmsgservice" in compact)
    )


def is_proactive_delivery_receipt_text(text: str) -> bool:
    raw = _single_line(text, 240)
    if not raw:
        return False
    compact = re.sub(r"[\s。.!！?？,，；;:：、~～\"'“”‘’（）()【】\[\]]+", "", raw).lower()
    if not compact:
        return False
    if compact in {
        "已发送",
        "发送成功",
        "发送完成",
        "发送完毕",
        "已成功发送",
        "消息已发送",
        "消息发送成功",
        "messagesent",
        "sent",
        "我主动开口了",
        "我主动发了一段语音",
        "我主动分享了一点东西",
        "我主动做了一次小互动",
    }:
        return True
    if re.fullmatch(r"(?:图|图片|照片)(?:好|好了|生成好了|出来了|完成了)[啦了]*", compact):
        return True
    if re.fullmatch(r"(?:生图|出图|图片生成)(?:完成|好了|成功)[啦了]*", compact):
        return True
    if re.search(r"(?:还在|正在|继续)?(?:排队|队列|等待生成|等图|等图片|等它出图)", compact):
        return True
    if re.match(r"^(?:已经|已)(?:发|发送)过去[啦了]?(?:等(?:着|他|你|对方)|等回复|等回我)?$", compact):
        return True
    if re.match(r"^等(?:着)?(?:他|你|对方)?回(?:我|复)?[啦了]*$", compact):
        return True
    if compact.startswith("消息已送达"):
        return True
    if re.match(r"^这是.{0,80}(?:发的|发送的|收到的).{0,80}(?:消息|打招呼|问候|回复)", compact):
        return True
    if re.match(r"^这(?:条|是).{0,80}(?:语气|内容|消息).{0,80}$", compact):
        return True
    receipt_prefixes = (
        "消息已发送给",
        "消息发送给",
        "已发送给",
        "已经发送给",
        "已向",
        "已经向",
    )
    receipt_descriptors = (
        "讲的是",
        "说的是",
        "内容是",
        "内容就是",
        "发的是",
        "转述的是",
        "分享的是",
        "告诉的是",
    )
    if compact.startswith(receipt_prefixes) and any(token in compact for token in receipt_descriptors):
        return True
    long_receipt_markers = (
        ("已经把", "转给"),
        ("已把", "转给"),
        ("已经将", "转给"),
        ("已将", "转给"),
        ("已经发给", "就假装"),
        ("已经发送给", "就假装"),
        ("就假装", "语气很自然"),
        ("随手分享", "语气很自然"),
    )
    if any(all(token in raw for token in pair) for pair in long_receipt_markers):
        return True
    if (
        any(token in compact for token in ("视频链接转给", "链接转给", "消息转给", "内容转给"))
        and any(token in compact for token in ("已经", "已", "完成", "成功"))
    ):
        return True
    return (
        len(compact) <= 32
        and any(token in compact for token in ("发送给用户", "发给用户", "发送给对方", "发给对方", "发出去了"))
        and any(token in compact for token in ("已", "已经", "完成", "成功"))
    )


def strip_proactive_delivery_receipt_lines(text: str) -> str:
    kept = [
        line
        for raw_line in str(text or "").splitlines()
        if (line := raw_line.strip()) and not is_proactive_delivery_receipt_text(line)
    ]
    return "\n".join(kept).strip()
