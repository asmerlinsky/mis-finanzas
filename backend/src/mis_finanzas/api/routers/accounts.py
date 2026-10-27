from fastapi import APIRouter, status
from sqlalchemy import select

from mis_finanzas.api.common import commit_or_409, get_or_404
from mis_finanzas.api.deps import SessionDep
from mis_finanzas.api.schemas import AccountIn, AccountOut
from mis_finanzas.ledger.models import Account

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountOut])
def list_accounts(session: SessionDep) -> list[Account]:
    return list(session.scalars(select(Account).order_by(Account.name)))


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def create_account(body: AccountIn, session: SessionDep) -> Account:
    account = Account(**body.model_dump())
    session.add(account)
    commit_or_409(session, "account")
    return account


@router.put("/{account_id}", response_model=AccountOut)
def update_account(account_id: int, body: AccountIn, session: SessionDep) -> Account:
    account = get_or_404(session, Account, account_id)
    for key, value in body.model_dump().items():
        setattr(account, key, value)
    commit_or_409(session, "account")
    return account


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(account_id: int, session: SessionDep) -> None:
    """Fails with 409 while the account still has transactions or imports."""
    session.delete(get_or_404(session, Account, account_id))
    commit_or_409(session, "account")
