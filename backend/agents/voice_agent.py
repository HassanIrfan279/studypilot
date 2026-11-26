"""Voice agent: relays the browser's microphone to the Gemini Live API and streams the spoken
answer back. Gemini can call the same tools as the text chat while talking.

Browser -> server: binary = 16-bit PCM mono 16 kHz audio; text = JSON {"type": "text"|"announce", "text"}
Server -> browser: binary = 16-bit PCM mono 24 kHz audio; text = JSON events (transcripts, turn state)
"""
import asyncio
import json

from fastapi import WebSocket, WebSocketDisconnect
from google.genai import types

from activity_log import log
from agents.assistant_tools import ALL_TOOLS, SYSTEM_INSTRUCTION, TOOLS_BY_NAME
from config import GEMINI_LIVE_MODEL
from gemini import client


def _live_config():
    decls = [types.FunctionDeclaration.from_callable(client=client._api_client, callable=f)
             for f in ALL_TOOLS]
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=SYSTEM_INSTRUCTION + " You are speaking out loud: keep answers short "
                                                "and natural. If the student speaks Urdu, reply in Urdu.",
        tools=[types.Tool(function_declarations=decls)],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )


async def _run_tool(fc):
    fn = TOOLS_BY_NAME.get(fc.name)
    log("Voice", f"🛠 Tool call: {fc.name}({', '.join(map(str, (fc.args or {}).values()))})")
    if not fn:
        return {"error": f"unknown tool {fc.name}"}
    try:
        return await asyncio.to_thread(fn, **(fc.args or {}))
    except Exception as e:
        log("Voice", f"Tool {fc.name} failed: {e}", "error")
        return {"error": str(e)}


async def voice_session(ws: WebSocket):
    await ws.accept()
    if client is None:
        await ws.send_text(json.dumps({"type": "error", "text": "GEMINI_API_KEY missing"}))
        await ws.close()
        return
    try:
        async with client.aio.live.connect(model=GEMINI_LIVE_MODEL, config=_live_config()) as session:
            log("Voice", "🎙 Voice session started.")
            await ws.send_text(json.dumps({"type": "ready"}))

            async def browser_to_gemini():
                while True:
                    msg = await ws.receive()
                    if msg.get("type") == "websocket.disconnect":
                        raise WebSocketDisconnect()
                    if msg.get("bytes"):
                        await session.send_realtime_input(
                            audio=types.Blob(data=msg["bytes"], mime_type="audio/pcm;rate=16000"))
                    elif msg.get("text"):
                        data = json.loads(msg["text"])
                        text = data.get("text", "")
                        if data.get("type") == "announce":
                            text = ("(System notice — say this to the student out loud now, "
                                    f"in a natural way): {text}")
                        await session.send_client_content(
                            turns=types.Content(role="user", parts=[types.Part(text=text)]),
                            turn_complete=True)

            async def gemini_to_browser():
                while True:
                    async for resp in session.receive():
                        if resp.data:
                            await ws.send_bytes(resp.data)
                        sc = resp.server_content
                        if sc:
                            if sc.input_transcription and sc.input_transcription.text:
                                await ws.send_text(json.dumps({"type": "transcript", "role": "user",
                                                               "text": sc.input_transcription.text}))
                            if sc.output_transcription and sc.output_transcription.text:
                                await ws.send_text(json.dumps({"type": "transcript", "role": "agent",
                                                               "text": sc.output_transcription.text}))
                            if sc.interrupted:
                                await ws.send_text(json.dumps({"type": "interrupted"}))
                            if sc.turn_complete:
                                await ws.send_text(json.dumps({"type": "turn_complete"}))
                        if resp.tool_call:
                            results = []
                            for fc in resp.tool_call.function_calls:
                                out = await _run_tool(fc)
                                results.append(types.FunctionResponse(id=fc.id, name=fc.name,
                                                                      response={"result": out}))
                            await session.send_tool_response(function_responses=results)

            tasks = [asyncio.create_task(browser_to_gemini()), asyncio.create_task(gemini_to_browser())]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
            for t in pending:
                t.cancel()
            for t in done:
                if t.exception() and not isinstance(t.exception(), WebSocketDisconnect):
                    raise t.exception()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log("Voice", f"Voice session error: {e}", "error")
        try:
            await ws.send_text(json.dumps({"type": "error", "text": str(e)}))
        except Exception:
            pass
    finally:
        log("Voice", "Voice session ended.")
