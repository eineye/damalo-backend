from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ExpertContent
from app.schemas import ContentCreate, ContentReview
from app.rag import ingest_content
from app.documents import extract_text

router = APIRouter(prefix="/contents", tags=["contents"])


@router.post("")
def create_content(payload: ContentCreate, db: Session = Depends(get_db)):
    """전문가 노하우 입력 (모바일 앱에서 호출).
    음성/영상은 STT 처리 후 raw_text에 텍스트를 담아 이 엔드포인트를 호출한다고 가정.
    신규 콘텐츠는 기본적으로 'pending' 상태 -> 관리자 승인 전까지 챗봇 검색에 노출되지 않음."""
    content = ExpertContent(**payload.model_dump())
    db.add(content)
    db.commit()
    db.refresh(content)
    return {"id": content.id, "status": content.status}


@router.post("/upload")
async def upload_document(
    tenant_id: str = Form(...),
    author_name: str = Form("관리자"),
    process_tag: str | None = Form(None),
    equipment_tag: str | None = Form(None),
    risk_level: str = Form("low"),
    auto_approve: bool = Form(True),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """관리자 웹의 매뉴얼/문서 대량 업로드용. PDF/DOCX/TXT/MD를 받아 텍스트를 추출하고
    ExpertContent로 등록한다 (content_type='document'). auto_approve=True(기본값)면
    등록과 동시에 승인 처리되어 바로 청킹+임베딩까지 진행된다 (관리자 본인이 올리는 공식 문서라는 전제)."""
    raw = await file.read()
    text = extract_text(file.filename, raw)

    content = ExpertContent(
        tenant_id=tenant_id,
        author_name=author_name,
        content_type="document",
        raw_text=text,
        media_url=None,
        process_tag=process_tag,
        equipment_tag=equipment_tag,
        risk_level=risk_level,
        status="approved" if auto_approve else "pending",
        reviewed_by=author_name if auto_approve else None,
    )
    db.add(content)
    db.commit()
    db.refresh(content)

    chunk_count = 0
    if content.status == "approved":
        chunk_count = ingest_content(db, content)

    return {
        "id": content.id,
        "filename": file.filename,
        "status": content.status,
        "chars_extracted": len(text),
        "chunks_indexed": chunk_count,
    }


@router.get("")
def list_contents(
    tenant_id: str,
    status: str | None = None,
    content_type: str | None = None,
    db: Session = Depends(get_db),
):
    """관리자 웹 - 콘텐츠 목록 조회 (검수 큐 / 문서 목록 공용)"""
    q = db.query(ExpertContent).filter(ExpertContent.tenant_id == tenant_id)
    if status:
        q = q.filter(ExpertContent.status == status)
    if content_type:
        q = q.filter(ExpertContent.content_type == content_type)
    items = q.order_by(ExpertContent.created_at.desc()).all()
    return [
        {
            "id": c.id, "author_name": c.author_name, "content_type": c.content_type,
            "raw_text": c.raw_text, "process_tag": c.process_tag, "equipment_tag": c.equipment_tag,
            "risk_level": c.risk_level, "status": c.status, "created_at": c.created_at,
        } for c in items
    ]


@router.delete("/{content_id}")
def delete_content(content_id: str, db: Session = Depends(get_db)):
    """콘텐츠 삭제 (연결된 청크도 함께 삭제됨 - cascade 설정)."""
    content = db.query(ExpertContent).filter(ExpertContent.id == content_id).first()
    if not content:
        raise HTTPException(status_code=404, detail="content not found")
    db.delete(content)
    db.commit()
    return {"deleted": content_id}


@router.patch("/{content_id}/review")
def review_content(content_id: str, payload: ContentReview, db: Session = Depends(get_db)):
    """관리자 승인/반려. 승인 시 즉시 청킹+임베딩하여 RAG 검색 대상에 포함시킴."""
    content = db.query(ExpertContent).filter(ExpertContent.id == content_id).first()
    if not content:
        raise HTTPException(status_code=404, detail="content not found")

    content.status = payload.status
    content.reviewed_by = payload.reviewed_by
    db.commit()
    db.refresh(content)

    chunk_count = 0
    if payload.status == "approved":
        chunk_count = ingest_content(db, content)

    return {"id": content.id, "status": content.status, "chunks_indexed": chunk_count}
