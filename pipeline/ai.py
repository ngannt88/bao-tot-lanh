"""Gọi Claude Code ở chế độ không giao diện (claude -p), tắt hết công cụ, ép JSON."""
from __future__ import annotations
import json, os, re, shutil, subprocess, time
from typing import Any
from common import setup_logging

log = setup_logging()

MODEL_ALIAS = {"haiku": "haiku", "sonnet": "sonnet", "opus": "opus"}
THINKING_TOKENS = 0   # có thể ghi đè từ config scoring.thinking_tokens


class AIError(RuntimeError):
    pass


def _claude_bin() -> str:
    exe = shutil.which("claude") or shutil.which("claude.cmd")
    if not exe:
        raise AIError("Không tìm thấy lệnh 'claude'. Cài: npm install -g @anthropic-ai/claude-code")
    return exe


def _extract_json(text: str) -> Any:
    """Lấy khối JSON đầu tiên trong chuỗi (phòng model nói thêm chữ ngoài JSON)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        i = text.find(opener)
        if i < 0:
            continue
        depth = 0
        for j in range(i, len(text)):
            if text[j] == opener:
                depth += 1
            elif text[j] == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[i:j + 1])
                    except json.JSONDecodeError:
                        break
    raise AIError("Không tách được JSON từ trả lời của model: " + text[:300])


def ask_json(prompt: str, *, system: str, model: str, schema: dict | None = None,
             retries: int = 2, timeout: int = 300, thinking: int | None = None) -> Any:
    """Gửi prompt, nhận JSON. Thử lại khi lỗi mạng hoặc JSON hỏng.
    thinking: số token suy nghĩ tối đa (None = dùng THINKING_TOKENS, mặc định 0 = tắt)."""
    cmd = [_claude_bin(), "-p", "--model", MODEL_ALIAS.get(model, model),
           "--output-format", "json", "--tools", "", "--no-session-persistence",
           "--permission-mode", "dontAsk", "--system-prompt", system,
           "--effort", "low"]                      # chấm điểm không cần suy nghĩ sâu: nhanh hơn, ít token hơn
    if schema and False:  # --json-schema không hoạt động ở chế độ này, giữ tham số cho tương thích
        cmd += ["--json-schema", json.dumps(schema, ensure_ascii=False)]
    env = dict(os.environ, PYTHONIOENCODING="utf-8", CLAUDE_CODE_DISABLE_TELEMETRY="1")
    # Dùng gói Claude đã đăng nhập, KHÔNG dùng API key trả phí nếu máy có sẵn biến này
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    env["MAX_THINKING_TOKENS"] = str(THINKING_TOKENS if thinking is None else thinking)   # 0 = tắt suy nghĩ ẩn (trước đây chiếm ~90% token ra)
    last = None
    for attempt in range(retries + 1):
        t0 = time.time()
        try:
            r = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=timeout, env=env, shell=False)
        except subprocess.TimeoutExpired:
            last = AIError(f"claude -p quá {timeout}s")
            log.warning("AI timeout (lần %d)", attempt + 1)
            continue
        out = r.stdout.strip()
        try:
            envelope = json.loads(out) if out.startswith("{") else {"result": out}
        except json.JSONDecodeError:
            envelope = {"result": out}
        if envelope.get("is_error") or r.returncode != 0 and not envelope.get("result"):
            msg = envelope.get("result") or r.stderr.strip()[:300] or f"exit {r.returncode}"
            last = AIError(f"claude -p lỗi: {msg}")
            if "Not logged in" in msg or "login" in msg.lower():
                raise last
            log.warning("AI lỗi (lần %d): %s", attempt + 1, msg[:200])
            time.sleep(3 * (attempt + 1))
            continue
        usage = envelope.get("usage") or {}
        think = (usage.get("output_tokens_details") or {}).get("thinking_tokens", "?")
        log.info("AI %s: %.1fs, in=%s (cache %s) out=%s (suy nghĩ %s)", model, time.time() - t0,
                 usage.get("input_tokens", "?"), usage.get("cache_read_input_tokens", "?"),
                 usage.get("output_tokens", "?"), think)
        if schema and envelope.get("structured_output") is not None:
            return envelope["structured_output"]
        try:
            return _extract_json(envelope.get("result", ""))
        except AIError as e:
            last = e
            log.warning("JSON hỏng (lần %d)", attempt + 1)
    raise last or AIError("AI thất bại")


def check_login() -> tuple[bool, str]:
    """Kiểm tra CLI đã đăng nhập chưa, trả (ok, thông điệp)."""
    try:
        out = ask_json("Trả về JSON {\"ok\": true}", system="Chỉ trả JSON.", model="haiku",
                       schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
                       retries=0, timeout=90)
        return bool(out.get("ok")), "đã đăng nhập"
    except AIError as e:
        return False, str(e)
