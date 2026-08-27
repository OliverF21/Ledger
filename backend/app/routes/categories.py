"""
Category and categorization rule endpoints.
- GET /categorization-rules: list all rules with category info
- POST /categorization-rules: create a rule (merchant pattern -> category)
- DELETE /categorization-rules/{id}: remove a rule
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.categorization import (
    apply_rule_to_existing_transactions,
    get_active_rules,
    revert_deleted_rule_from_existing_transactions,
)
from app.database import get_db
from app.errors import log_and_raise
from app.models import CategoryRule, Category

router = APIRouter(tags=["categories"])


class RuleItem(BaseModel):
    id: int
    merchant_pattern: str
    description_pattern: Optional[str] = None
    category_name: str
    category_color: Optional[str]


class RulesResponse(BaseModel):
    rules: list[RuleItem]


@router.get("/categorization-rules", response_model=RulesResponse)
async def get_categorization_rules(db: Session = Depends(get_db)):
    """List all categorization rules with their category info."""
    try:
        rows = (
            db.query(CategoryRule, Category)
            .join(Category, CategoryRule.category_id == Category.id)
            .filter(CategoryRule.user_id == 1)
            .order_by(func.coalesce(CategoryRule.priority, CategoryRule.id).asc())
            .all()
        )

        rules = [
            RuleItem(
                id=rule.id,
                merchant_pattern=rule.merchant_pattern,
                description_pattern=rule.description_pattern,
                category_name=category.name,
                category_color=category.color,
            )
            for rule, category in rows
        ]

        return RulesResponse(rules=rules)

    except Exception as e:
        log_and_raise(e)


class CreateRuleRequest(BaseModel):
    merchant_pattern: str
    description_pattern: Optional[str] = None
    category_name: str
    color: Optional[str] = None


class CreateRuleResponse(BaseModel):
    success: bool
    id: int
    applied_to_existing: int


def _find_or_create_category(db: Session, name: str, color: Optional[str] = None) -> Category:
    """Find a category by name for user 1, creating it (with optional color) if missing."""
    category = db.query(Category).filter(
        Category.user_id == 1,
        Category.name == name,
    ).first()
    if not category:
        category = Category(user_id=1, name=name, color=color)
        db.add(category)
        db.flush()
    return category


@router.post("/categorization-rules", response_model=CreateRuleResponse)
async def create_categorization_rule(req: CreateRuleRequest, db: Session = Depends(get_db)):
    """
    Create a merchant-pattern -> category rule. Creates the category if it
    doesn't exist, and immediately backfills any existing non-manually-
    categorized transactions that match the pattern.
    """
    try:
        pattern = req.merchant_pattern.strip()
        description_pattern = req.description_pattern.strip() if req.description_pattern else None
        category_name = req.category_name.strip()
        if not pattern or not category_name:
            raise HTTPException(status_code=400, detail="merchant_pattern and category_name are required")

        category = _find_or_create_category(db, category_name, req.color)

        rule = CategoryRule(
            user_id=1, category_id=category.id, merchant_pattern=pattern, description_pattern=description_pattern
        )
        db.add(rule)
        db.flush()

        applied = apply_rule_to_existing_transactions(db, pattern, category_name, description_pattern=description_pattern)
        db.commit()

        return CreateRuleResponse(success=True, id=rule.id, applied_to_existing=applied)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_and_raise(e, status_code=400)


class ReorderRulesRequest(BaseModel):
    rule_ids: list[int]


@router.put("/categorization-rules/reorder")
async def reorder_categorization_rules(req: ReorderRulesRequest, db: Session = Depends(get_db)):
    """
    Set explicit match priority for rules: the full new order, assigned
    priority = index in that list. Declared before the {rule_id} route so
    "reorder" is never mistaken for an id (also safe regardless of order,
    since {rule_id} is int-typed and won't match non-numeric paths).
    """
    try:
        rules = db.query(CategoryRule).filter(
            CategoryRule.id.in_(req.rule_ids),
            CategoryRule.user_id == 1,
        ).all()
        if len(rules) != len(req.rule_ids):
            raise HTTPException(status_code=400, detail="One or more rule_ids not found")

        rules_by_id = {r.id: r for r in rules}
        for index, rule_id in enumerate(req.rule_ids):
            rules_by_id[rule_id].priority = index
        db.commit()

        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_and_raise(e, status_code=400)


class UpdateRuleRequest(BaseModel):
    merchant_pattern: str
    description_pattern: Optional[str] = None
    category_name: str
    color: Optional[str] = None


@router.put("/categorization-rules/{rule_id}", response_model=CreateRuleResponse)
async def update_categorization_rule(rule_id: int, req: UpdateRuleRequest, db: Session = Depends(get_db)):
    """
    Update a rule's merchant pattern and/or target category. Creates the
    category if it doesn't exist, and re-backfills the (possibly new)
    pattern onto existing non-manually-categorized transactions. Does not
    revert categories the rule's previous pattern already applied - same
    limitation DELETE already documents.
    """
    try:
        pattern = req.merchant_pattern.strip()
        description_pattern = req.description_pattern.strip() if req.description_pattern else None
        category_name = req.category_name.strip()
        if not pattern or not category_name:
            raise HTTPException(status_code=400, detail="merchant_pattern and category_name are required")

        rule = db.query(CategoryRule).filter(CategoryRule.id == rule_id, CategoryRule.user_id == 1).first()
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")

        category = _find_or_create_category(db, category_name, req.color)

        rule.merchant_pattern = pattern
        rule.description_pattern = description_pattern
        rule.category_id = category.id
        db.flush()

        applied = apply_rule_to_existing_transactions(db, pattern, category_name, description_pattern=description_pattern)
        db.commit()

        return CreateRuleResponse(success=True, id=rule.id, applied_to_existing=applied)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_and_raise(e, status_code=400)


@router.delete("/categorization-rules/{rule_id}")
async def delete_categorization_rule(rule_id: int, db: Session = Depends(get_db)):
    """Remove a rule and recalculate any non-manual transactions it auto-categorized."""
    rule = db.query(CategoryRule).filter(CategoryRule.id == rule_id, CategoryRule.user_id == 1).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    try:
        remaining_rules = [
            rule_row
            for rule_row in get_active_rules(db)
            if rule_row[0].id != rule.id
        ]
        reverted = revert_deleted_rule_from_existing_transactions(
            db,
            merchant_pattern=rule.merchant_pattern,
            remaining_rules=remaining_rules,
            description_pattern=rule.description_pattern,
        )
        db.delete(rule)
        db.commit()
        return {"success": True, "reverted_transactions": reverted}
    except Exception as e:
        db.rollback()
        log_and_raise(e, status_code=400)
