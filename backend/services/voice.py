"""
语音入口 —— 纯开源方案

前端: MediaRecorder → WebSocket
后端: faster-whisper → Intent Router
"""

import io

# faster-whisper 与 Hermes STT 共享同一引擎
try:
    from faster_whisper import WhisperModel

    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False


class VoiceService:
    """语音转文字 + 意图路由"""

    def __init__(self, model_size: str = "tiny"):
        self.model = None
        self.model_size = model_size
        if WHISPER_AVAILABLE:
            self.model = WhisperModel(model_size, device="cpu", compute_type="int8")

    async def transcribe(self, audio_bytes: bytes, format: str = "webm") -> str:
        """
        接收浏览器录音 → 转文字

        format: webm (浏览器默认) / wav
        """
        if not self.model:
            return ""

        # webm → wav 转换(如需要)
        if format == "webm":
            audio_bytes = self._webm_to_wav(audio_bytes)

        segments, _ = self.model.transcribe(
            io.BytesIO(audio_bytes),
            language="zh",
            beam_size=5,
            vad_filter=True,
        )
        text = " ".join(seg.text for seg in segments)
        return text.strip()

    async def route(self, text: str) -> dict:
        """
        意图识别 → 路由到对应 Agent/Skill

        简化版: 关键词匹配 → 后期升级为 LLM 语义路由
        """
        intent_map = {
            "写代码": "ai-coding",
            "生成代码": "ai-coding",
            "对话": "chatbot",
            "聊天": "chatbot",
            "发邮件": "office-copilot",
            "总结": "office-copilot",
            "视频": "video-gen",
            "生成视频": "video-gen",
            "调查": "research",
            "分析": "research",
        }

        for keyword, scene_id in intent_map.items():
            if keyword in text:
                return {"intent": scene_id, "text": text}

        return {"intent": "unknown", "text": text}

    def _webm_to_wav(self, data: bytes) -> bytes:
        """webm → wav 转换(ffmpeg pipeline)"""
        import subprocess

        proc = subprocess.run(
            [
                "ffmpeg",
                "-i",
                "pipe:0",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-f",
                "wav",
                "pipe:1",
            ],
            input=data,
            capture_output=True,
            timeout=10,
        )
        return proc.stdout
