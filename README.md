# 제조 노하우 RAG 백엔드 (프로토타입)

FastAPI + PostgreSQL(pgvector) + Anthropic API로 구성된 RAG 백엔드입니다.
카카오톡 챗봇과 관리자 웹이 모두 이 서버를 호출합니다.

## 1. 준비물
- PostgreSQL 15+ (pgvector 확장)
- Python 3.11+
- Anthropic API Key

## 2. 설치
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 값 채우기 (DATABASE_URL, ANTHROPIC_API_KEY 등)
```

DB에 pgvector 확장 활성화:
```sql
CREATE DATABASE knowhow_rag;
\c knowhow_rag
CREATE EXTENSION IF NOT EXISTS vector;
```

## 3. 실행
```bash
uvicorn app.main:app --reload --port 8000
```
최초 실행 시 테이블이 자동 생성됩니다(개발용). 운영 배포 시 Alembic 마이그레이션으로 전환하세요.

## 4. 기본 사용 흐름 테스트

**① 테넌트(공장) 생성**
```bash
curl -X POST "http://localhost:8000/admin/tenants?name=서울금속가공&kakao_channel_id=chan_001"
```

**② 전문가 노하우 등록** (모바일 앱에서 STT 처리 후 텍스트로 전송한다고 가정)
```bash
curl -X POST http://localhost:8000/contents \
  -H "Content-Type: application/json" \
  -d '{
        "tenant_id": "<위에서 받은 tenant_id>",
        "author_name": "김기술",
        "content_type": "voice",
        "raw_text": "3호기 베어링 교체 시 반드시 전원을 차단하고 5분 대기 후 작업합니다. 그리스는 SK-2 제품만 사용하세요.",
        "process_tag": "베어링 교체",
        "equipment_tag": "3호기",
        "risk_level": "medium"
      }'
```

**③ 관리자 승인** (승인 즉시 임베딩되어 검색 가능해짐)
```bash
curl -X PATCH http://localhost:8000/contents/<content_id>/review \
  -H "Content-Type: application/json" \
  -d '{"status": "approved", "reviewed_by": "관리자A"}'
```

**④ 질의 (카카오톡 스킬서버가 내부적으로 호출하는 것과 동일한 로직)**
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "<tenant_id>", "question": "3호기 베어링 교체할 때 뭘 조심해야 해?"}'
```

## 5. 매뉴얼/문서 대량 업로드 (관리자 웹 전용)

현장에서 입력하기 어려운 기존 매뉴얼/규정 PDF·Word 파일을 관리자가 한꺼번에 올려서
자동으로 텍스트 추출 → 청킹 → 임베딩까지 처리합니다. 지원 형식: **PDF, DOCX, TXT, MD**.

⚠️ **배포 전 필수: DB에 이미 만들어진 `content_type` enum 타입에 값 추가 필요**
(기존 배포 DB는 새 값을 모르는 상태라 그대로 두면 업로드 시 에러가 납니다)
Supabase SQL Editor에서 한 번만 실행:
```sql
ALTER TYPE content_type ADD VALUE IF NOT EXISTS 'document';
```

**업로드 (curl 예시, 실제로는 관리자 웹에서 파일 선택으로 처리)**
```bash
curl -X POST https://damal-backend.onrender.com/contents/upload \
  -F "tenant_id=<tenant_id>" \
  -F "author_name=관리자" \
  -F "process_tag=안전관리" \
  -F "risk_level=medium" \
  -F "auto_approve=true" \
  -F "file=@안전보건규정.pdf"
```
`auto_approve=true`(기본값)면 업로드 즉시 승인되어 바로 챗봇 검색에 반영됩니다.
검수를 거치고 싶으면 `auto_approve=false`로 올린 뒤 관리자 웹의 "검수 대기함"에서 승인하세요.

**주의**
- 스캔본(이미지) PDF는 텍스트 추출이 안 됩니다 (OCR 미지원) - 텍스트 기반 PDF만 가능
- 아주 큰 문서(수백 페이지)는 청킹+임베딩에 시간이 걸려 무료 요금제에서 타임아웃 날 수 있습니다 - 안 되면 문서를 장(chapter) 단위로 나눠서 올려보세요

## 6. 음성/영상 → 텍스트 변환 (STT)
`faster-whisper`로 로컬에서 동작합니다 (API 키 불필요, 최초 실행 시 모델 자동 다운로드).
영상 파일 처리에는 시스템에 `ffmpeg`가 설치되어 있어야 합니다.
```bash
# Ubuntu/Debian
sudo apt-get install -y ffmpeg
```

```bash
curl -X POST http://localhost:8000/stt \
  -F "file=@recording.m4a"
# -> {"text": "3호기 베어링 교체 시..."}
```

반환된 `text`를 그대로 `/contents`의 `raw_text`로 넘기면 됩니다.
한국어 산업 용어 인식률이 낮으면 `app/routers/stt.py`의 `transcribe_local`을
네이버 Clova Speech 등 유상 API로 교체하세요(파일 내 예시 주석 참고).

## 7. 현장 공통 가이드/사규 문서 - 입력 토큰 비용 절감 (Claude 프롬프트 캐싱)

안전수칙, 사규처럼 **자주 반복 질문되는 대용량 정적 문서**는 개별 노하우(RAG)와 별도 경로로 등록해서
질문마다 문서 전체를 다시 과금하지 않도록 캐싱합니다. 별도 API 키나 외부 서비스 없이 지금 쓰는
Anthropic API 안에서 바로 동작합니다 (`cache_control` 파라미터만 추가).

**등록**
```bash
curl -X POST http://localhost:8000/guides \
  -H "Content-Type: application/json" \
  -d '{
        "tenant_id": "<tenant_id>",
        "title": "안전보건관리규정",
        "content": "<규정 전문 텍스트, 길수록 캐싱 효과가 큼>"
      }'
```

**질문**
```bash
curl -X POST http://localhost:8000/guides/<guide_id>/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "화기 작업 시 필요한 허가 절차는?"}'
```

응답의 `usage`에서 실제 절감 효과를 바로 확인할 수 있습니다:
```json
{
  "answer": "...",
  "usage": {
    "input_tokens": 12,
    "output_tokens": 180,
    "cache_read_input_tokens": 15000,     // 캐시에서 읽음 - 정가의 10%만 과금
    "cache_creation_input_tokens": 0       // 최초 1회 호출에서만 값이 생김 (정가의 1.25~2배)
  }
}
```
같은 문서로 두 번째 질문부터 `cache_creation_input_tokens`는 0이 되고 `cache_read_input_tokens`가
채워지면서, 그 부분 입력 비용이 약 90% 절감됩니다.

**참고**
- 캐시는 문서 내용이 100% 동일할 때만 적중합니다. 문서를 수정하면 다음 호출은 다시 "쓰기" 비용이 듭니다.
- 문서가 너무 짧으면(대략 1,000~4,000토큰 미만, 모델마다 다름) 캐싱 자체가 걸리지 않고 매번 정상 과금됩니다 - 정말 긴 정적 문서에만 효과가 있습니다.
- 기본 TTL은 `.env`의 `GUIDE_CACHE_TTL`로 조절 (`5m`=무료 기본값, `1h`=쓰기 비용 2배지만 오래 유지). 질문이 5분 넘게 뜸하면 `1h`을 권장합니다.

## 8. 카카오 오픈빌더 연결
1. 카카오 i 오픈빌더 콘솔에서 봇 생성
2. 스킬(Skill) 등록 시 URL을 `https://<배포도메인>/kakao/webhook/<tenant_id>` 로 설정
3. 폴백 블록(정해진 시나리오에 없는 발화)에 이 스킬을 연결
4. 공장마다 별도 봇(또는 별도 tenant_id)을 두면 지식베이스가 자동으로 격리됩니다

## 9. Dify로 만든 챗봇을 카카오톡에 연결 (자체 RAG 챗봇과 별개)

Dify는 카카오톡 채널을 기본 지원하지 않아서, 이 백엔드가 중계 역할을 합니다.

1. Dify 앱 화면 → 왼쪽 메뉴 **API 접근(API Access)** → API 키 발급
2. Render(또는 배포 환경) 환경변수에 추가:
   ```
   DIFY_API_KEY=app-xxxxxxxxxxxxxxxx
   DIFY_API_BASE=https://api.dify.ai/v1   # 셀프호스팅이면 그 서버 주소
   ```
3. 카카오 i 오픈빌더 콘솔 → 스킬 URL을 다음으로 등록:
   ```
   https://<배포도메인>/kakao-dify/webhook/<tenant_id>
   ```
4. 폴백 블록에 이 스킬 연결

`tenant_id`는 자체 RAG 챗봇과 마찬가지로 공장/채널 구분용 임의 값이면 됩니다 (Dify 쪽 대화 자체는
`user` 파라미터로 카카오 사용자별로 분리되고, `dify_sessions` 테이블이 대화 맥락(conversation_id)을
자동으로 이어줍니다). 자체 RAG 챗봇(`/kakao/webhook/...`)과 Dify 챗봇(`/kakao-dify/webhook/...`)
중 하나만 카카오 스킬에 연결하시면 됩니다 - 같은 오픈빌더 봇에 폴백을 두 개 등록할 순 없어요.

## 10. 다음 단계 (프로토타입 → 실서비스)
- STT 연동: 음성/영상 업로드 → Clova Speech 등으로 변환 → `/contents`로 전송하는 워커 추가
- 비동기 처리: 임베딩/STT는 Celery/RQ 등 큐로 분리 (현재는 동기 처리)
- 인증: 관리자 API에 JWT 인증 추가, 카카오 webhook에 시크릿 검증 추가
- 마이그레이션: Alembic 도입
- 모니터링: 응답 지연/오류율, LLM 비용 트래킹
