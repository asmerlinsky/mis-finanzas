from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from mis_finanzas.api.common import commit_or_409, get_or_404
from mis_finanzas.api.deps import SessionDep
from mis_finanzas.api.schemas import CategoryIn, CategoryOut, RuleIn, RuleOut
from mis_finanzas.ledger.categorize import apply_rules_to_uncategorized
from mis_finanzas.ledger.models import Category, CategoryRule
from mis_finanzas.ledger.rules import validate_pattern

router = APIRouter(tags=["categories"])


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(session: SessionDep) -> list[Category]:
    return list(session.scalars(select(Category).order_by(Category.name)))


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(body: CategoryIn, session: SessionDep) -> Category:
    category = Category(**body.model_dump())
    session.add(category)
    commit_or_409(session, "category")
    return category


@router.put("/categories/{category_id}", response_model=CategoryOut)
def update_category(category_id: int, body: CategoryIn, session: SessionDep) -> Category:
    category = get_or_404(session, Category, category_id)
    category.name, category.kind = body.name, body.kind
    commit_or_409(session, "category")
    return category


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, session: SessionDep) -> None:
    """Its transactions become uncategorized; its rules are deleted."""
    session.delete(get_or_404(session, Category, category_id))
    commit_or_409(session, "category")


@router.get("/rules", response_model=list[RuleOut])
def list_rules(session: SessionDep) -> list[CategoryRule]:
    query = select(CategoryRule).order_by(CategoryRule.priority, CategoryRule.id)
    return list(session.scalars(query))


def _validated_rule_fields(body: RuleIn, session: Session) -> dict[str, object]:
    try:
        validate_pattern(body.pattern, body.match_type)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    get_or_404(session, Category, body.category_id)
    return body.model_dump()


@router.post("/rules", response_model=RuleOut, status_code=status.HTTP_201_CREATED)
def create_rule(body: RuleIn, session: SessionDep) -> CategoryRule:
    rule = CategoryRule(**_validated_rule_fields(body, session))
    session.add(rule)
    commit_or_409(session, "rule")
    return rule


@router.put("/rules/{rule_id}", response_model=RuleOut)
def update_rule(rule_id: int, body: RuleIn, session: SessionDep) -> CategoryRule:
    rule = get_or_404(session, CategoryRule, rule_id)
    for key, value in _validated_rule_fields(body, session).items():
        setattr(rule, key, value)
    commit_or_409(session, "rule")
    return rule


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: int, session: SessionDep) -> None:
    session.delete(get_or_404(session, CategoryRule, rule_id))
    session.commit()


@router.post("/rules/apply")
def apply_rules(session: SessionDep) -> dict[str, int]:
    """Categorize every uncategorized, non-transfer transaction with the current rules."""
    return {"categorized": apply_rules_to_uncategorized(session)}
