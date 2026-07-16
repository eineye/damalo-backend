"""
음성/영상 업로드 -> 텍스트 변환(STT) 엔드포인트.

기본 구현: faster-whisper (로컬 실행, API 키 불필요, 다국어 지원)
운영 환경에서 한국어 산업 용어 인식률이 부족하면 아래 TranscribeProvider를
네이버 Clova Speech / Google STT 등으로 교체하세요. 인터페이스만 맞추면
router 코드는 수정할 필요가 없습니다.
"""
import tempfile
import os
from functools import lru_cache

from fastapi import APIRouter, UploadFile, File, HTTPException

router = APIRouter(prefix="/stt", tags=["stt"])


@lru_cache(maxsize=1)
def _get_whisper_model():
    from faster_whisper import WhisperModel
    # "small" 모델 기준 CPU에서도 동작. 정확도가 더 필요하면 "medium"/"large-v3"로 교체.
    return WhisperModel("small", device="cpu", compute_type="int8")


def transcribe_local(file_path: str) -> str:
    model = _get_whisper_model()
    segments, _ = model.transcribe(file_path, language="ko", vad_filter=True)
    return " ".join(seg.text.strip() for seg in segments)


# --- 대체 구현 예시 (Clova Speech로 교체 시) ---
# def transcribe_clova(file_path: str) -> str:
#     import requests
#     with open(file_path, "rb") as f:
#         resp = requests.post(
#             CLOVA_INVOKE_URL,
#             headers={"X-CLOVASPEECH-API-KEY": CLOVA_SECRET},
#             files={"media": f},
#             data={"language": "ko-KR"},
#         )
#     return resp.json()["text"]


@router.post("")
async def speech_to_text(file: UploadFile = File(...)):
    """모바일 앱이 녹음/촬영한 음성·영상 파일을 업로드하면 텍스트를 반환.
    영상 파일도 오디오 트랙만 자동으로 읽어 처리됩니다(ffmpeg 필요)."""
    suffix = os.path.splitext(file.filename or "")[1] or ".m4a"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        text = transcribe_local(tmp_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"STT 처리 실패: {e}")
    finally:
        os.remove(tmp_path)

    if not text.strip():
        raise HTTPException(status_code=422, detail="음성에서 텍스트를 추출하지 못했습니다. 다시 녹음해주세요.")

    return {"text": text.strip()}
