from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.base import get_session
from app.schemas.contracts import (
    DashboardResponse,
    Envelope,
    MaterialResponse,
    OrderDetailResponse,
    OrderResponse,
    RiskResponse,
    RiskStatusUpdate,
)
from app.services import briefing


router = APIRouter(prefix="/api")


@router.get("/dashboard", response_model=Envelope[DashboardResponse])
def get_dashboard(session: Session = Depends(get_session)) -> Envelope[DashboardResponse]:
    return Envelope(data=briefing.get_dashboard(session))


@router.get("/orders", response_model=Envelope[list[OrderResponse]])
def get_orders(session: Session = Depends(get_session)) -> Envelope[list[OrderResponse]]:
    return Envelope(data=briefing.list_orders(session))


@router.get("/orders/{order_id}", response_model=Envelope[OrderDetailResponse])
def get_order(
    order_id: int,
    session: Session = Depends(get_session),
) -> Envelope[OrderDetailResponse]:
    order = briefing.get_order(session, order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="오더를 찾을 수 없습니다.",
        )
    return Envelope(data=order)


@router.get("/materials", response_model=Envelope[list[MaterialResponse]])
def get_materials(
    session: Session = Depends(get_session),
) -> Envelope[list[MaterialResponse]]:
    return Envelope(data=briefing.list_materials(session))


@router.get("/risks", response_model=Envelope[list[RiskResponse]])
def get_risks(session: Session = Depends(get_session)) -> Envelope[list[RiskResponse]]:
    return Envelope(data=briefing.list_risks(session))


@router.patch(
    "/risks/{risk_id}/status",
    response_model=Envelope[RiskResponse],
)
def update_risk_status(
    risk_id: str,
    payload: RiskStatusUpdate,
    session: Session = Depends(get_session),
) -> Envelope[RiskResponse]:
    risk = briefing.update_risk_status(session, risk_id, payload.status)
    if risk is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="리스크를 찾을 수 없습니다.",
        )
    return Envelope(data=risk)
