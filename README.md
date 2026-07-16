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

## 5. 음성/영상 → 텍스트 변환 (STT)
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

## 6. 카카오 오픈빌더 연결
1. 카카오 i 오픈빌더 콘솔에서 봇 생성
2. 스킬(Skill) 등록 시 URL을 `https://<배포도메인>/kakao/webhook/<tenant_id>` 로 설정
3. 폴백 블록(정해진 시나리오에 없는 발화)에 이 스킬을 연결
4. 공장마다 별도 봇(또는 별도 tenant_id)을 두면 지식베이스가 자동으로 격리됩니다

## 7. 다음 단계 (프로토타입 → 실서비스)
- STT 연동: 음성/영상 업로드 → Clova Speech 등으로 변환 → `/contents`로 전송하는 워커 추가
- 비동기 처리: 임베딩/STT는 Celery/RQ 등 큐로 분리 (현재는 동기 처리)
- 인증: 관리자 API에 JWT 인증 추가, 카카오 webhook에 시크릿 검증 추가
- 마이그레이션: Alembic 도입
- 모니터링: 응답 지연/오류율, LLM 비용 트래킹
