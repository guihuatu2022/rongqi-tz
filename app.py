import asyncio
import os
import time
import uuid
from datetime import datetime, timezone

from aiohttp import web


STARTED_AT = datetime.now(timezone.utc)
INSTANCE_ID = uuid.uuid4().hex[:12]

REQUESTS_TOTAL = 0
WS_OPENED = 0
WS_CLOSED = 0
WS_ACTIVE = 0


def get_port():
    return int(os.getenv("PORT", "8080"))


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def uptime_seconds():
    return int((datetime.now(timezone.utc) - STARTED_AT).total_seconds())


def mib(value):
    return round(value / 1024 / 1024, 2)


def base_info():
    return {
        "version": "v0.2.0-python",
        "instance_id": INSTANCE_ID,
        "started_at": STARTED_AT.isoformat(),
        "uptime_seconds": uptime_seconds(),
        "listen_port": get_port(),
    }


async def count_request(request):
    global REQUESTS_TOTAL
    REQUESTS_TOTAL += 1


@web.middleware
async def request_middleware(request, handler):
    await count_request(request)

    try:
        response = await handler(request)
    except web.HTTPException:
        raise
    except Exception as error:
        return web.json_response(
            {
                "ok": False,
                "error": str(error),
                "instance_id": INSTANCE_ID,
            },
            status=500,
        )

    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Probe-Instance"] = INSTANCE_ID
    response.headers["X-Probe-Version"] = "v0.2.0-python"

    return response


async def home(request):
    return web.Response(
        text=HTML_PAGE,
        content_type="text/html",
        charset="utf-8",
    )


async def healthz(request):
    return web.json_response(
        {
            "ok": True,
            "message": "容器正常运行",
            "time": now_utc(),
            "instance_id": INSTANCE_ID,
        }
    )


async def readyz(request):
    return web.json_response(
        {
            "ready": True,
            "listen_port": get_port(),
            "uptime_seconds": uptime_seconds(),
            "instance_id": INSTANCE_ID,
        }
    )


async def report(request):
    return web.json_response(
        {
            **base_info(),
            "requests_total": REQUESTS_TOTAL,
            "websocket": {
                "opened": WS_OPENED,
                "closed": WS_CLOSED,
                "active": WS_ACTIVE,
            },
        }
    )


async def headers(request):
    allowed_headers = [
        "Host",
        "User-Agent",
        "Accept",
        "Connection",
        "Upgrade",
        "Sec-WebSocket-Version",
        "Sec-WebSocket-Protocol",
        "X-Forwarded-For",
        "X-Forwarded-Proto",
        "X-Real-IP",
        "CF-Connecting-IP",
        "CF-Ray",
        "CF-IPCountry",
        "Via",
    ]

    received_headers = {}

    for key in allowed_headers:
        value = request.headers.get(key)
        if value:
            received_headers[key] = value[:300]

    return web.json_response(
        {
            "method": request.method,
            "path": request.path,
            "query": request.query_string,
            "scheme_seen_by_container": request.scheme,
            "host": request.host,
            "remote": request.remote,
            "headers": received_headers,
        }
    )


async def websocket_handler(request):
    global WS_OPENED, WS_CLOSED, WS_ACTIVE

    ws = web.WebSocketResponse(
        autoping=True,
        heartbeat=25,
        max_msg_size=1024 * 1024,
    )

    await ws.prepare(request)

    WS_OPENED += 1
    WS_ACTIVE += 1
    connected_at = time.time()

    try:
        await ws.send_json(
            {
                "event": "connected",
                "instance_id": INSTANCE_ID,
                "time": now_utc(),
            }
        )

        async for message in ws:
            if message.type == web.WSMsgType.TEXT:
                await ws.send_str(message.data)

            elif message.type == web.WSMsgType.BINARY:
                await ws.send_bytes(message.data)

            elif message.type == web.WSMsgType.ERROR:
                break

    finally:
        WS_ACTIVE -= 1
        WS_CLOSED += 1

        print(
            {
                "event": "websocket_closed",
                "instance_id": INSTANCE_ID,
                "duration_seconds": round(time.time() - connected_at, 2),
                "close_code": ws.close_code,
            },
            flush=True,
        )

    return ws


HTML_PAGE = r"""
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gcore CaaS 容器探针</title>
<style>
body {
  font-family: Arial, "Microsoft YaHei", sans-serif;
  background: #f4f7fb;
  margin: 0;
  color: #172033;
}
.box {
  max-width: 760px;
  margin: 28px auto;
  padding: 26px;
  background: white;
  border-radius: 14px;
  box-shadow: 0 4px 18px rgba(0,0,0,.10);
}
h1 {
  margin-top: 0;
}
button {
  border: 0;
  border-radius: 8px;
  background: #1769e0;
  color: white;
  padding: 11px 15px;
  margin: 5px 6px 5px 0;
  font-size: 15px;
  cursor: pointer;
}
button:hover {
  background: #0d53bd;
}
#status {
  margin: 15px 0;
  color: #5d6b80;
}
.ok {
  color: #16813b !important;
}
.bad {
  color: #b42318 !important;
}
pre {
  min-height: 200px;
  box-sizing: border-box;
  padding: 15px;
  border-radius: 9px;
  background: #101827;
  color: #dceaff;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
.tip {
  color: #5d6b80;
  line-height: 1.6;
}
</style>
</head>

<body>
<main class="box">
  <h1>Gcore CaaS 容器探针</h1>

  <p class="tip">
    当前只检测 Gcore CaaS 容器本身。容器默认监听端口为 8080。
  </p>

  <button id="basicButton">1. 开始基础检测</button>
  <button id="wsButton">2. 测试 WebSocket</button>
  <button id="idleButton">3. 开始 10 分钟长连接</button>
  <button id="copyButton">复制检测结果</button>

  <p id="status">等待开始。</p>

  <pre id="result">请先点击“开始基础检测”。</pre>
</main>

<script>
"use strict";

const output = document.getElementById("result");
const status = document.getElementById("status");

const result = {
  schema: "gcore-caas-probe/v2",
  entry_url: window.location.origin,
  basic: null,
  websocket: null,
  long_connection: null
};

function showResult() {
  result.generated_at = new Date().toISOString();
  output.textContent = JSON.stringify(result, null, 2);
}

function setStatus(text, type) {
  status.textContent = text;
  status.className = type || "";
}

async function getJson(path) {
  const start = performance.now();

  const response = await fetch(path, {
    cache: "no-store"
  });

  let data;

  try {
    data = await response.json();
  } catch (error) {
    data = {
      read_json_error: String(error)
    };
  }

  return {
    ok: response.ok,
    status: response.status,
    latency_ms: Math.round(performance.now() - start),
    data: data
  };
}

async function basicTest() {
  setStatus("正在检测容器，请稍等……", "");

  try {
    const checks = await Promise.all([
      getJson("/healthz"),
      getJson("/readyz"),
      getJson("/api/report"),
      getJson("/api/headers")
    ]);

    result.basic = {
      healthz: checks[0],
      readyz: checks[1],
      report: checks[2],
      headers: checks[3]
    };

    const passed = checks.every(function(item) {
      return item.ok;
    });

    if (passed) {
      setStatus("基础检测完成：正常。", "ok");
    } else {
      setStatus("基础检测完成：存在异常，请复制结果。", "bad");
    }

  } catch (error) {
    result.basic = {
      ok: false,
      error: String(error)
    };

    setStatus("基础检测失败。", "bad");
  }

  showResult();
}

function makeWsUrl() {
  const prefix = window.location.protocol === "https:" ? "wss://" : "ws://";
  return prefix + window.location.host + "/ws";
}

function wsTest() {
  setStatus("正在测试 WebSocket……", "");

  const started = performance.now();
  let finished = false;
  let socket;

  function finish(ok, message, extra) {
    if (finished) {
      return;
    }

    finished = true;

    result.websocket = {
      ok: ok,
      message: message,
      elapsed_ms: Math.round(performance.now() - started),
      extra: extra || null
    };

    if (ok) {
      setStatus("WebSocket 测试成功。", "ok");
    } else {
      setStatus("WebSocket 测试失败：" + message, "bad");
    }

    showResult();

    try {
      socket.close();
    } catch (error) {
    }
  }

  try {
    socket = new WebSocket(makeWsUrl());
    socket.binaryType = "arraybuffer";
  } catch (error) {
    finish(false, String(error));
    return;
  }

  const timer = setTimeout(function() {
    finish(false, "15 秒内未完成数据回显");
  }, 15000);

  socket.onopen = function() {
    const bytes = new Uint8Array(65536);

    for (let i = 0; i < bytes.length; i++) {
      bytes[i] = i % 256;
    }

    socket.send(bytes);
  };

  socket.onmessage = function(event) {
    if (event.data instanceof ArrayBuffer) {
      clearTimeout(timer);

      finish(
        event.data.byteLength === 65536,
        "收到二进制回显",
        {
          expected_bytes: 65536,
          received_bytes: event.data.byteLength
        }
      );
    }
  };

  socket.onerror = function() {
    clearTimeout(timer);
    finish(false, "浏览器报告 WebSocket 错误");
  };

  socket.onclose = function(event) {
    if (!finished) {
      clearTimeout(timer);
      finish(false, "连接关闭，代码：" + event.code);
    }
  };
}

function longConnectionTest() {
  setStatus("正在建立连接，10 分钟测试开始后请不要刷新页面……", "");

  const startTime = Date.now();
  let finished = false;
  let socket;

  function finish(ok, message, closeCode) {
    if (finished) {
      return;
    }

    finished = true;

    result.long_connection = {
      ok: ok,
      result: message,
      duration_seconds: Math.round((Date.now() - startTime) / 1000),
      close_code: closeCode || null
    };

    if (ok) {
      setStatus("长连接测试成功：10 分钟未异常断开。", "ok");
    } else {
      setStatus("长连接提前断开：" + message, "bad");
    }

    showResult();

    try {
      socket.close();
    } catch (error) {
    }
  }

  try {
    socket = new WebSocket(makeWsUrl());
  } catch (error) {
    finish(false, String(error));
    return;
  }

  const timer = setTimeout(function() {
    finish(true, "10 分钟内未异常断开", 1000);
  }, 600000);

  socket.onopen = function() {
    setStatus("已连接，正在进行 10 分钟长连接测试，请保持网页打开……", "");
  };

  socket.onerror = function() {
  };

  socket.onclose = function(event) {
    if (!finished) {
      clearTimeout(timer);
      finish(false, "关闭代码：" + event.code, event.code);
    }
  };
}

async function copyResult() {
  showResult();

  const text = "【Gcore CaaS 容器探针结果】\n\n" + output.textContent;

  try {
    await navigator.clipboard.writeText(text);
    setStatus("已复制，请直接粘贴给我。", "ok");
  } catch (error) {
    setStatus("自动复制失败，请手动复制下方内容。", "");
  }
}

document.getElementById("basicButton").addEventListener("click", basicTest);
document.getElementById("wsButton").addEventListener("click", wsTest);
document.getElementById("idleButton").addEventListener("click", longConnectionTest);
document.getElementById("copyButton").addEventListener("click", copyResult);
</script>
</body>
</html>
"""


app = web.Application(middlewares=[request_middleware])

app.router.add_get("/", home)
app.router.add_get("/healthz", healthz)
app.router.add_get("/readyz", readyz)
app.router.add_get("/api/report", report)
app.router.add_get("/api/headers", headers)
app.router.add_get("/ws", websocket_handler)

if __name__ == "__main__":
    print(
        {
            "event": "probe_started",
            "port": get_port(),
            "instance_id": INSTANCE_ID,
            "started_at": STARTED_AT.isoformat(),
        },
        flush=True,
    )

    web.run_app(
        app,
        host="0.0.0.0",
        port=get_port(),
        access_log=None,
    )
