# app/routers/family_tree_router.py

from __future__ import annotations

from datetime import datetime
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload


from app.database import SessionLocal
from app.auth import get_current_user
from app.models.user import User
from app.core.profile_access import get_current_user_profile

from app.routers.profile_router import attach_media_urls
from app.utils.urls import absolute_media_url

from app.models.profile import Profile

from app.models.family_tree import FamilyTree
from app.models.family_tree_node import FamilyTreeNode
from app.models.family_tree_invite import FamilyTreeInvite
from app.models.family_tree_merge_request import FamilyTreeMergeRequest

from app.models.family_union import FamilyUnion
from app.models.union_child import UnionChild

from app.schemas.family_tree_schema import (
    FamilyTreeCreate,
    FamilyTreeOut,
    FamilyTreeNodeCreate,
    FamilyTreeNodeOut,
    FamilyTreeEdgeCreate,
    FamilyTreeAssignChildCreate,
)

from app.schemas.family_tree_invite_schema import (
    FamilyTreeInviteCreate,
    FamilyTreeInviteOut,
)

from app.schemas.family_tree_merge_schema import (
    FamilyTreeMergeRequestCreate,
    FamilyTreeMergeRequestOut,
)

router = APIRouter(prefix="/family/tree", tags=["Family Tree"])


# ============================================================
# DB DEP
# ============================================================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================
# HELPERS
# ============================================================

def _now() -> datetime:
    return datetime.utcnow()


def resolve_tree(db: Session, tree_id: int) -> tuple[FamilyTree, Optional[int]]:
    """
    Returns (effective_tree, redirected_from_tree_id).

    If requested tree is archived and has merged_into_tree_id,
    redirect to the target tree and tell caller where it came from.
    """
    tree = db.query(FamilyTree).filter(FamilyTree.id == tree_id).first()
    if not tree:
        raise HTTPException(404, "Tree not found")

    if getattr(tree, "is_archived", False) and getattr(tree, "merged_into_tree_id", None):
        target_id = tree.merged_into_tree_id
        target = db.query(FamilyTree).filter(FamilyTree.id == target_id).first()
        if target:
            return target, tree.id

    return tree, None


def require_tree_exists(db: Session, tree_id: int) -> FamilyTree:
    tree = db.query(FamilyTree).filter(FamilyTree.id == tree_id).first()
    if not tree:
        raise HTTPException(404, "Tree not found")
    return tree


def my_confirmed_in_tree(db: Session, tree_id: int, my_profile_id: str) -> bool:
    node = (
        db.query(FamilyTreeNode)
        .filter(
            FamilyTreeNode.tree_id == tree_id,
            FamilyTreeNode.profile_id == my_profile_id,
            FamilyTreeNode.is_confirmed == True,  # noqa: E712
        )
        .first()
    )
    return node is not None


def require_tree_access(db: Session, tree_id: int, my_profile_id: str):
    """
    Tree access rule (no roles):
    - creator can always access
    - OR confirmed node in tree can access
    """
    tree = db.query(FamilyTree).filter(FamilyTree.id == tree_id).first()
    if not tree:
        raise HTTPException(404, "Tree not found")

    if tree.created_by_profile_id == my_profile_id:
        return

    if my_confirmed_in_tree(db, tree_id, my_profile_id):
        return

    raise HTTPException(403, "You do not have access to this tree")


def require_confirmed_in_tree(db: Session, tree_id: int, my_profile_id: str, message: str):
    if not my_confirmed_in_tree(db, tree_id, my_profile_id):
        raise HTTPException(403, message)


def require_node_in_tree(db: Session, tree_id: int, node_id: int) -> FamilyTreeNode:
    node = (
        db.query(FamilyTreeNode)
        .filter(FamilyTreeNode.id == node_id, FamilyTreeNode.tree_id == tree_id)
        .first()
    )
    if not node:
        raise HTTPException(404, "Node not found in this tree")
    return node


def _profile_image_url(db: Session, profile: Profile | None) -> Optional[str]:
    if not profile:
        return None
    urls = attach_media_urls(db, profile)
    image_url = urls.get("profile_picture_url")
    if image_url:
        return absolute_media_url(image_url)
    return None


def _serialize_tree_basic(tree: FamilyTree) -> dict[str, Any]:
    return {
        "id": tree.id,
        "name": tree.name,
        "created_by_profile_id": tree.created_by_profile_id,
        "created_at": getattr(tree, "created_at", None),
        "is_archived": getattr(tree, "is_archived", False),
        "merged_into_tree_id": getattr(tree, "merged_into_tree_id", None),
        "archived_at": getattr(tree, "archived_at", None),
    }


def _serialize_node(db: Session, node: FamilyTreeNode) -> dict[str, Any]:
    profile = getattr(node, "profile", None)

    # ✅ NEW: Detect if this node has a pending invite
    has_pending_invite = (
        db.query(FamilyTreeInvite)
        .filter(
            FamilyTreeInvite.node_id == node.id,
            FamilyTreeInvite.status == "pending",
        )
        .first()
        is not None
    )

    return {
        "id": node.id,
        "tree_id": node.tree_id,
        "display_name": node.display_name,
        "profile_id": node.profile_id,

        # Same pattern as group router
        "profile_image_url": _profile_image_url(db, profile),

        "gender": getattr(node, "gender", None),
        "date_of_birth": getattr(node, "date_of_birth", None),
        "date_of_death": getattr(node, "date_of_death", None),

        "created_at": getattr(node, "created_at", None),
        "is_confirmed": bool(getattr(node, "is_confirmed", False)),
        "confirmed_at": getattr(node, "confirmed_at", None),

        # ✅ IMPORTANT: Send this to Flutter
        "has_pending_invite": has_pending_invite,
    }


def _serialize_invite(db: Session, inv: FamilyTreeInvite) -> dict[str, Any]:
    # ---------------------------
    # Load inviter profile
    # ---------------------------
    inviter_profile = None
    if inv.invited_by_profile_id:
        inviter_profile = (
            db.query(Profile)
            .filter(Profile.id == inv.invited_by_profile_id)
            .first()
        )

    # ---------------------------
    # Load invited profile
    # ---------------------------
    invited_profile = None
    if inv.invited_profile_id:
        invited_profile = (
            db.query(Profile)
            .filter(Profile.id == inv.invited_profile_id)
            .first()
        )

    # ---------------------------
    # Load node name
    # ---------------------------
    node = (
        db.query(FamilyTreeNode)
        .filter(FamilyTreeNode.id == inv.node_id)
        .first()
    )

    return {
        "id": inv.id,
        "tree_id": inv.tree_id,
        "node_id": inv.node_id,

        # ---------------------------
        # Node context
        # ---------------------------
        "node_display_name": node.display_name if node else None,

        # ---------------------------
        # Inviter (who sent it)
        # ---------------------------
        "invited_by_profile_id": inv.invited_by_profile_id,
        "invited_by_name": inviter_profile.full_name if inviter_profile else None,
        "invited_by_image_url": _profile_image_url(db, inviter_profile),

        # ---------------------------
        # Invited person (who receives)
        # ---------------------------
        "invited_profile_id": inv.invited_profile_id,
        "invited_profile_name": invited_profile.full_name if invited_profile else None,
        "invited_profile_image_url": _profile_image_url(db, invited_profile),

        # ---------------------------
        # Email fallback
        # ---------------------------
        "invited_email": inv.invited_email,

        # ---------------------------
        # Status + timestamps
        # ---------------------------
        "status": inv.status,
        "created_at": inv.created_at,
        "responded_at": getattr(inv, "responded_at", None),
    }
def _serialize_merge_request(db: Session, req: FamilyTreeMergeRequest) -> dict[str, Any]:
    # ---------------------------
    # Load requester profile
    # ---------------------------
    requester = (
        db.query(Profile)
        .filter(Profile.id == req.requested_by_profile_id)
        .first()
    )

    # ---------------------------
    # Load trees
    # ---------------------------
    from_tree = (
        db.query(FamilyTree)
        .filter(FamilyTree.id == req.from_tree_id)
        .first()
    )

    to_tree = (
        db.query(FamilyTree)
        .filter(FamilyTree.id == req.to_tree_id)
        .first()
    )

    return {
        "id": req.id,

        # ---------------------------
        # Tree IDs
        # ---------------------------
        "from_tree_id": req.from_tree_id,
        "to_tree_id": req.to_tree_id,

        # ---------------------------
        # Tree names (NEW)
        # ---------------------------
        "from_tree_name": from_tree.name if from_tree else None,
        "to_tree_name": to_tree.name if to_tree else None,

        # ---------------------------
        # Requester info (NEW)
        # ---------------------------
        "requested_by_profile_id": req.requested_by_profile_id,
        "requested_by_name": requester.full_name if requester else None,
        "requested_by_image_url": _profile_image_url(db, requester),

        # ---------------------------
        # Message + status
        # ---------------------------
        "message": req.message or "",
        "status": req.status,

        # ---------------------------
        # Dates
        # ---------------------------
        "created_at": req.created_at,
        "responded_at": getattr(req, "responded_at", None),
    }

def trees_share_confirmed_profile(db, tree_a: int, tree_b: int) -> bool:
    shared = (
        db.query(FamilyTreeNode.profile_id)
        .filter(
            FamilyTreeNode.tree_id.in_([tree_a, tree_b]),
            FamilyTreeNode.profile_id.isnot(None),
            FamilyTreeNode.is_confirmed == True,
        )
        .group_by(FamilyTreeNode.profile_id)
        .having(db.func.count() >= 2)
        .first()
    )
    return shared is not None


# ============================================================
# CREATE TREE
# (matches group: POST "")
# ============================================================

@router.post("", response_model=FamilyTreeOut)
def create_tree(
    payload: FamilyTreeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user.id)

    # ----------------------------
    # Create the tree
    # ----------------------------
    tree = FamilyTree(
        name=payload.name,
        created_by_profile_id=me.id,
        created_at=_now(),
        is_archived=False,
        merged_into_tree_id=None,
        archived_at=None,
    )

    db.add(tree)
    db.commit()
    db.refresh(tree)

    # ----------------------------
    # AUTO-CREATE "ME" NODE
    # Always confirmed in my own tree
    # ----------------------------
    me_node = FamilyTreeNode(
        tree_id=tree.id,
        display_name=getattr(me, "full_name", None) or "Me",
        profile_id=me.id,
        is_confirmed=True,
        confirmed_at=_now(),
        created_at=_now(),
    )

    db.add(me_node)
    db.commit()

    return tree



# ============================================================
# MY TREES (matches group: GET /mine)
# ============================================================

@router.get("/mine")
def my_trees(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns trees I created OR trees where I have a node (confirmed or not).
    """
    me = get_current_user_profile(db, current_user.id)

    trees = (
        db.query(FamilyTree)
        .outerjoin(FamilyTreeNode, FamilyTreeNode.tree_id == FamilyTree.id)
        .filter(
            (FamilyTree.created_by_profile_id == me.id)
            | (FamilyTreeNode.profile_id == me.id)
        )
        .distinct()
        .order_by(FamilyTree.id.desc())
        .all()
    )

    return [_serialize_tree_basic(t) for t in trees]


# ============================================================
# SEARCH (matches group: GET /search)
# ============================================================

@router.get("/search")
def search_trees(
    query: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = get_current_user_profile(db, current_user.id)

    q = (query or "").strip()
    if len(q) < 2:
        return []

    trees = (
        db.query(FamilyTree)
        .filter(FamilyTree.is_archived == False)  # noqa: E712
        .filter(FamilyTree.name.ilike(f"%{q}%"))
        .order_by(FamilyTree.name.asc())
        .limit(25)
        .all()
    )

    return [_serialize_tree_basic(t) for t in trees]


# ============================================================
# RENAME (matches group: PUT /{id}/rename)
# ============================================================

@router.put("/{tree_id}/rename")
def rename_tree(
    tree_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Payload: {"name": "..."}
    Any user with tree access can rename (creator or confirmed node).
    """
    me = get_current_user_profile(db, current_user.id)
    tree = require_tree_exists(db, tree_id)

    if getattr(tree, "is_archived", False):
        raise HTTPException(400, "Cannot rename an archived tree")

    require_tree_access(db, tree.id, me.id)

    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Tree name cannot be empty")

    tree.name = name
    db.commit()
    return {"status": "renamed", "name": tree.name}


# ============================================================
# ARCHIVE / DELETE (matches group: DELETE /{id})
# ============================================================

@router.delete("/{tree_id}")
def delete_tree(
    tree_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Archives tree (soft delete), like group router.
    Only creator can archive.
    """
    me = get_current_user_profile(db, current_user.id)
    tree = require_tree_exists(db, tree_id)

    if tree.created_by_profile_id != me.id:
        raise HTTPException(403, "Creator only")

    if getattr(tree, "is_archived", False):
        return {"status": "already_archived"}

    tree.is_archived = True
    tree.archived_at = _now()
    db.commit()
    return {"status": "archived"}


# ============================================================
# GET TREE FULL (nodes + GENERATED edges)
# ============================================================

@router.get("/{tree_id}")
def get_tree(
    tree_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns nodes + GENERATED edges.
    - partner edges come from FamilyUnion
    - parent_child edges come from UnionChild
    """
    me = get_current_user_profile(db, current_user.id)

    tree, redirected_from = resolve_tree(db, tree_id)

    # enforce privacy on effective tree id
    require_tree_access(db, tree.id, me.id)

    nodes = (
    db.query(FamilyTreeNode)
    .options(joinedload(FamilyTreeNode.profile))
    .filter(FamilyTreeNode.tree_id == tree.id)
    .all()
)

    unions = db.query(FamilyUnion).filter(FamilyUnion.tree_id == tree.id).all()
    child_links = db.query(UnionChild).filter(UnionChild.tree_id == tree.id).all()

    edges: list[dict[str, Any]] = []

    # partner edges
    for u in unions:
        edges.append({
            "id": f"union-{u.id}",
            "tree_id": tree.id,
            "from_node_id": u.partner_a_node_id,
            "to_node_id": u.partner_b_node_id,
            "kind": "partner",
            "notes": None,
            "is_confirmed": False,
        })

    union_by_id = {u.id: u for u in unions}

    # parent-child edges
    for link in child_links:
        if link.union_id:
            u = union_by_id.get(link.union_id)
            if u:
                edges.append({
                    "id": f"uc-{link.id}-a",
                    "tree_id": tree.id,
                    "from_node_id": u.partner_a_node_id,
                    "to_node_id": link.child_node_id,
                    "kind": "parent_child",
                    "notes": None,
                    "is_confirmed": False,
                })
                edges.append({
                    "id": f"uc-{link.id}-b",
                    "tree_id": tree.id,
                    "from_node_id": u.partner_b_node_id,
                    "to_node_id": link.child_node_id,
                    "kind": "parent_child",
                    "notes": None,
                    "is_confirmed": False,
                })
        elif link.single_parent_id:
            edges.append({
                "id": f"uc-{link.id}",
                "tree_id": tree.id,
                "from_node_id": link.single_parent_id,
                "to_node_id": link.child_node_id,
                "kind": "parent_child",
                "notes": None,
                "is_confirmed": False,
            })

    out = _serialize_tree_basic(tree)
    out["nodes"] = [_serialize_node(db, n) for n in nodes]
    out["edges"] = edges

    if redirected_from:
        out["redirected_from_tree_id"] = redirected_from

    return out


# ============================================================
# GET NODE BY ID
# ============================================================

@router.get("/node/{node_id}")
def get_tree_node(
    node_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user.id)

    node = (
    db.query(FamilyTreeNode)
    .options(joinedload(FamilyTreeNode.profile))
    .filter(FamilyTreeNode.id == node_id)
    .first()
)

    if not node:
        raise HTTPException(404, "Node not found")

    require_tree_access(db, node.tree_id, me.id)

    tree, redirected_from = resolve_tree(db, node.tree_id)

    out = _serialize_node(db, node)
    if redirected_from:
        out["redirected_from_tree_id"] = redirected_from
        out["effective_tree_id"] = tree.id
    return out


# ============================================================
# NODE CREATE
# ============================================================

@router.post("/{tree_id}/node", response_model=FamilyTreeNodeOut)
def add_node(
    tree_id: int,
    payload: FamilyTreeNodeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user.id)

    tree, _ = resolve_tree(db, tree_id)
    require_tree_access(db, tree.id, me.id)

    # ============================================================
    # ✅ SAFETY: Prevent duplicate "Me" node
    # ============================================================
    if payload.profile_id == me.id:
        existing = (
            db.query(FamilyTreeNode)
            .filter(
                FamilyTreeNode.tree_id == tree.id,
                FamilyTreeNode.profile_id == me.id,
            )
            .first()
        )

        if existing:
            raise HTTPException(
                status_code=400,
                detail="Your profile is already attached in this tree",
            )

    # ============================================================
    # Create node
    # ============================================================
    node = FamilyTreeNode(
        tree_id=tree.id,
        display_name=payload.display_name,
        profile_id=getattr(payload, "profile_id", None),
        gender=getattr(payload, "gender", None),
        date_of_birth=getattr(payload, "date_of_birth", None),
        date_of_death=getattr(payload, "date_of_death", None),
        is_confirmed=False,
        confirmed_at=None,
        created_at=_now(),
    )

    # ============================================================
    # ✅ Auto-confirm if user attaches THEIR OWN profile
    # ============================================================
    if getattr(payload, "profile_id", None) and payload.profile_id == me.id:
        node.is_confirmed = True
        node.confirmed_at = _now()

    db.add(node)
    db.commit()
    db.refresh(node)

    return node



# ============================================================
# EDGE CREATE
# - partner => union (dedupe)
# - parent_child => single-parent OR auto-union if parent has 1 partner
# ============================================================

@router.post("/{tree_id}/edge", response_model=dict)
def add_edge(
    tree_id: int,
    payload: FamilyTreeEdgeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user.id)

    # Resolve tree (handles merge redirects)
    tree, _ = resolve_tree(db, tree_id)
    require_tree_access(db, tree.id, me.id)

    # Ensure both nodes exist in this tree
    require_node_in_tree(db, tree.id, payload.from_node_id)
    require_node_in_tree(db, tree.id, payload.to_node_id)

    kind = (getattr(payload, "kind", None) or "parent_child").strip()

    if kind not in ("parent_child", "partner"):
        raise HTTPException(400, "Invalid edge kind")

    # ============================================================
    # PARTNER EDGE → CREATE UNION (DEDUPED)
    # ============================================================

    if kind == "partner":
        a = payload.from_node_id
        b = payload.to_node_id

        existing = (
            db.query(FamilyUnion)
            .filter(
                FamilyUnion.tree_id == tree.id,
                (
                    ((FamilyUnion.partner_a_node_id == a) &
                     (FamilyUnion.partner_b_node_id == b))
                    |
                    ((FamilyUnion.partner_a_node_id == b) &
                     (FamilyUnion.partner_b_node_id == a))
                ),
            )
            .first()
        )

        if existing:
            return {
                "id": f"union-{existing.id}",
                "tree_id": tree.id,
                "from_node_id": str(existing.partner_a_node_id),
                "to_node_id": str(existing.partner_b_node_id),
                "kind": "partner",
                "notes": None,
                "is_confirmed": False,
            }

        union = FamilyUnion(
            tree_id=tree.id,
            partner_a_node_id=a,
            partner_b_node_id=b,
            status="partner",
            created_at=_now(),
        )

        db.add(union)
        db.commit()
        db.refresh(union)

        return {
            "id": f"union-{union.id}",
            "tree_id": tree.id,
            "from_node_id": str(union.partner_a_node_id),
            "to_node_id": str(union.partner_b_node_id),
            "kind": "partner",
            "notes": None,
            "is_confirmed": False,
        }

    # ============================================================
    # PARENT-CHILD EDGE
    # ============================================================

    parent_id = payload.from_node_id
    child_id = payload.to_node_id

    # HARD RULE: Max 2 parents per child
    existing_parent_links = db.query(UnionChild).filter(
        UnionChild.tree_id == tree.id,
        UnionChild.child_node_id == child_id,
    ).all()

    if len(existing_parent_links) >= 2:
        raise HTTPException(
            status_code=400,
            detail="This person already has two parents.",
        )

    # Check if parent is in exactly one union
    parent_unions = db.query(FamilyUnion).filter(
        FamilyUnion.tree_id == tree.id,
        (
            (FamilyUnion.partner_a_node_id == parent_id)
            | (FamilyUnion.partner_b_node_id == parent_id)
        )
    ).all()

    # If parent has exactly one partner union → attach child to union
    if len(parent_unions) == 1:
        u = parent_unions[0]

        # Remove any existing single-parent link for this child
        db.query(UnionChild).filter(
            UnionChild.tree_id == tree.id,
            UnionChild.child_node_id == child_id,
            UnionChild.single_parent_id.isnot(None),
        ).delete(synchronize_session=False)

        link = UnionChild(
            tree_id=tree.id,
            child_node_id=child_id,
            union_id=u.id,
            single_parent_id=None,
            role="biological",
            created_at=_now(),
        )

        db.add(link)
        db.commit()
        db.refresh(link)

        return {
            "id": f"uc-{link.id}",
            "tree_id": tree.id,
            "from_node_id": str(parent_id),
            "to_node_id": str(child_id),
            "kind": "parent_child",
            "notes": None,
            "is_confirmed": False,
        }

    # Otherwise: single-parent link
    link = UnionChild(
        tree_id=tree.id,
        child_node_id=child_id,
        union_id=None,
        single_parent_id=parent_id,
        role="biological",
        created_at=_now(),
    )

    db.add(link)
    db.commit()
    db.refresh(link)

    return {
        "id": f"uc-{link.id}",
        "tree_id": tree.id,
        "from_node_id": str(parent_id),
        "to_node_id": str(child_id),
        "kind": "parent_child",
        "notes": None,
        "is_confirmed": False,
    }



# ============================================================
# ASSIGN CHILD TO TWO PARENTS (NEW)
# ============================================================

@router.post("/{tree_id}/assign-child")
def assign_child_to_two_parents(
    tree_id: int,
    payload: FamilyTreeAssignChildCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Explicitly assigns a child to TWO parents (union).

    This prevents guessing/inference.
    """

    me = get_current_user_profile(db, current_user.id)

    tree, _ = resolve_tree(db, tree_id)
    require_tree_access(db, tree.id, me.id)

    # Ensure all nodes exist
    child = require_node_in_tree(db, tree.id, payload.child_node_id)
    parent_a = require_node_in_tree(db, tree.id, payload.parent_a_node_id)
    parent_b = require_node_in_tree(db, tree.id, payload.parent_b_node_id)

    # ------------------------------------------------------------
    # Find or create union between the parents
    # ------------------------------------------------------------
    existing_union = (
        db.query(FamilyUnion)
        .filter(
            FamilyUnion.tree_id == tree.id,
            (
                ((FamilyUnion.partner_a_node_id == parent_a.id) &
                 (FamilyUnion.partner_b_node_id == parent_b.id))
                |
                ((FamilyUnion.partner_a_node_id == parent_b.id) &
                 (FamilyUnion.partner_b_node_id == parent_a.id))
            ),
        )
        .first()
    )

    if existing_union:
        union = existing_union
    else:
        union = FamilyUnion(
            tree_id=tree.id,
            partner_a_node_id=parent_a.id,
            partner_b_node_id=parent_b.id,
            status="partner",
            created_at=_now(),
        )
        db.add(union)
        db.commit()
        db.refresh(union)

    # ------------------------------------------------------------
    # Remove any existing single-parent link for this child
    # ------------------------------------------------------------
    db.query(UnionChild).filter(
    UnionChild.tree_id == tree.id,
    UnionChild.child_node_id == child.id,
    UnionChild.single_parent_id.isnot(None),
).delete(synchronize_session=False)

    # ------------------------------------------------------------
    # Create new union-child link
    # ------------------------------------------------------------
    link = UnionChild(
        tree_id=tree.id,
        child_node_id=child.id,
        union_id=union.id,
        single_parent_id=None,
        role="biological",
        created_at=_now(),
    )

    db.add(link)
    db.commit()
    db.refresh(link)

    return {
        "status": "assigned",
        "child_node_id": child.id,
        "union_id": union.id,
        "parent_a": union.partner_a_node_id,
        "parent_b": union.partner_b_node_id,
    }

# ============================================================
# NODE RENAME
# ============================================================

@router.post("/{tree_id}/node/{node_id}/rename")
def rename_node(
    tree_id: int,
    node_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user.id)

    tree, _ = resolve_tree(db, tree_id)
    require_tree_access(db, tree.id, me.id)

    node = require_node_in_tree(db, tree.id, node_id)

    new_name = (payload.get("display_name") or "").strip()
    if not new_name:
        raise HTTPException(400, "Name required")

    node.display_name = new_name
    db.commit()

    return {
        "status": "renamed",
        "id": node.id,
        "display_name": node.display_name,
    }

@router.delete("/{tree_id}/node/{node_id}")
def delete_node(
    tree_id: int,
    node_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user.id)

    tree, _ = resolve_tree(db, tree_id)
    require_tree_access(db, tree.id, me.id)

    node = require_node_in_tree(db, tree.id, node_id)

    # ============================================================
    # SAFETY RULE: Prevent deleting claimed confirmed nodes
    # ============================================================
    if node.profile_id and node.is_confirmed:
        raise HTTPException(
            status_code=400,
            detail="You cannot delete a claimed person. You may only detach them.",
        )

    # ============================================================
    # STEP 0: If this node is part of any unions,
    # dissolve those unions safely WITHOUT deleting children links.
    #
    # We convert union-children into single-parent children
    # linked to the remaining partner.
    # ============================================================

    unions = db.query(FamilyUnion).filter(
        FamilyUnion.tree_id == tree.id,
        (
            (FamilyUnion.partner_a_node_id == node.id)
            | (FamilyUnion.partner_b_node_id == node.id)
        )
    ).all()

    for u in unions:
        # Remaining partner becomes single parent after dissolution
        remaining_parent_id = (
            u.partner_b_node_id if u.partner_a_node_id == node.id else u.partner_a_node_id
        )

        # For every child currently attached to this union,
        # convert to single-parent link so children DO NOT disappear.
        union_children = db.query(UnionChild).filter(
            UnionChild.tree_id == tree.id,
            UnionChild.union_id == u.id,
        ).all()

        for link in union_children:
            link.union_id = None
            link.single_parent_id = remaining_parent_id

        # Now we can safely delete the union itself
        db.delete(u)

    # ============================================================
    # STEP 1: Remove parent-child links directly involving this node
    #
    # - If this node is the CHILD in any link -> remove those links
    # - If this node is a SINGLE parent in any link -> remove those links
    #
    # Note: union-based links referencing this node were already converted above.
    # ============================================================

    db.query(UnionChild).filter(
        UnionChild.tree_id == tree.id,
        (
            (UnionChild.child_node_id == node.id)
            | (UnionChild.single_parent_id == node.id)
        )
    ).delete(synchronize_session=False)

    # ============================================================
    # STEP 2: Remove pending invites for this node
    # ============================================================

    db.query(FamilyTreeInvite).filter(
        FamilyTreeInvite.tree_id == tree.id,
        FamilyTreeInvite.node_id == node.id,
        FamilyTreeInvite.status == "pending",
    ).delete(synchronize_session=False)

    # ============================================================
    # STEP 3: Delete ONLY this node
    # ============================================================

    db.delete(node)
    db.commit()

    return {"status": "deleted", "id": node_id}
# ============================================================
# INVITES (full lifecycle like group router)
# ============================================================

@router.post("/{tree_id}/invite")
def invite_to_node(
    tree_id: int,
    payload: FamilyTreeInviteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user.id)
    tree, _ = resolve_tree(db, tree_id)

    require_tree_access(db, tree.id, me.id)

    node = require_node_in_tree(db, tree.id, payload.node_id)

    if not payload.invited_profile_id and not payload.invited_email:
        raise HTTPException(
            400,
            "You must provide invited_profile_id or invited_email",
        )

    if node.profile_id and node.is_confirmed:
        raise HTTPException(
            400,
            "This node is already claimed and confirmed",
        )

        # ============================================================
    # ✅ HARD RULE: ONLY ONE pending invite per node
    # ============================================================

    existing_pending = (
        db.query(FamilyTreeInvite)
        .filter(
            FamilyTreeInvite.tree_id == tree.id,
            FamilyTreeInvite.node_id == node.id,
            FamilyTreeInvite.status == "pending",
        )
        .first()
    )

    if existing_pending:
        raise HTTPException(
            status_code=400,
            detail="This node already has a pending invite",
        )

    # ============================================================
    # Create invite
    # ============================================================

    invite = FamilyTreeInvite(
        tree_id=tree.id,
        node_id=node.id,
        invited_by_profile_id=me.id,
        invited_profile_id=payload.invited_profile_id,
        invited_email=payload.invited_email,
        status="pending",
        created_at=_now(),
        responded_at=None,
    )

    db.add(invite)
    db.commit()
    db.refresh(invite)

    return invite



@router.get("/invites/incoming")
def incoming_tree_invites(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user.id)

    invites = (
        db.query(FamilyTreeInvite)
        .filter(
            FamilyTreeInvite.invited_profile_id == me.id,
            FamilyTreeInvite.status == "pending",
        )
        .order_by(FamilyTreeInvite.created_at.desc())
        .all()
    )

    # ✅ FIXED
    return [_serialize_invite(db, i) for i in invites]


@router.get("/invites/outgoing")
def outgoing_tree_invites(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user.id)

    invites = (
        db.query(FamilyTreeInvite)
        .filter(
            FamilyTreeInvite.invited_by_profile_id == me.id,
            FamilyTreeInvite.status == "pending",
        )
        .order_by(FamilyTreeInvite.created_at.desc())
        .all()
    )

    # ✅ FIXED
    return [_serialize_invite(db, i) for i in invites]


# ============================================================
# NODE-SCOPED OUTGOING INVITES (NEW)
# ============================================================

@router.get("/{tree_id}/node/{node_id}/invites/outgoing")
def outgoing_invites_for_node(
    tree_id: int,
    node_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns ONLY pending invites I have sent
    for a specific node in a tree.

    This is used by NodeInviteSearch so Pending survives reload.
    """

    me = get_current_user_profile(db, current_user.id)

    # Resolve tree (handles merged redirect)
    tree, _ = resolve_tree(db, tree_id)

    # Must have access
    require_tree_access(db, tree.id, me.id)

    # Ensure node exists in this tree
    node = require_node_in_tree(db, tree.id, node_id)

    # Load invites
    invites = (
        db.query(FamilyTreeInvite)
        .filter(
            FamilyTreeInvite.tree_id == tree.id,
            FamilyTreeInvite.node_id == node.id,
            FamilyTreeInvite.invited_by_profile_id == me.id,
            FamilyTreeInvite.status == "pending",
        )
        .order_by(FamilyTreeInvite.created_at.desc())
        .all()
    )

    return [_serialize_invite(db, i) for i in invites]

@router.get("/{tree_id}/invites")
def list_tree_invites_for_tree(
    tree_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Like group router: list pending invites scoped to a tree (anyone with access can view).
    Includes node display name for UI convenience.
    """
    me = get_current_user_profile(db, current_user.id)
    tree, _ = resolve_tree(db, tree_id)
    require_tree_access(db, tree.id, me.id)

    rows = (
        db.query(FamilyTreeInvite, FamilyTreeNode)
        .join(FamilyTreeNode, FamilyTreeNode.id == FamilyTreeInvite.node_id)
        .filter(
            FamilyTreeInvite.tree_id == tree.id,
            FamilyTreeInvite.status == "pending",
        )
        .order_by(FamilyTreeInvite.created_at.desc())
        .all()
    )

    out = []
    for inv, node in rows:
        out.append({
            **_serialize_invite(db,inv),
            "node_display_name": node.display_name,
        })

    return out


@router.post("/invite/{invite_id}/cancel")
def cancel_invite(
    invite_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user.id)

    invite = db.query(FamilyTreeInvite).filter(FamilyTreeInvite.id == invite_id).first()
    if not invite:
        raise HTTPException(404, "Invite not found")

    # inviter only
    if invite.invited_by_profile_id != me.id:
        raise HTTPException(403, "Not authorised")

    if invite.status != "pending":
        return {"status": invite.status}

    invite.status = "cancelled"
    invite.responded_at = _now()
    db.commit()
    return {"status": "cancelled"}


@router.post("/invite/{invite_id}/accept")
def accept_invite(
    invite_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    invite = db.query(FamilyTreeInvite).filter(
        FamilyTreeInvite.id == invite_id
    ).first()

    if not invite or invite.status != "pending":
        raise HTTPException(404, "Invite not found")

    me = get_current_user_profile(db, current_user.id)

    # ------------------------------------------------------------
    # Only invited person can accept
    # ------------------------------------------------------------
    if invite.invited_profile_id != me.id:
        raise HTTPException(403, "Not authorised")

    # ------------------------------------------------------------
    # Load node being claimed
    # ------------------------------------------------------------
    node = db.query(FamilyTreeNode).filter(
        FamilyTreeNode.id == invite.node_id
    ).first()

    if not node:
        raise HTTPException(404, "Node not found")

    # ------------------------------------------------------------
    # STEP 1: Attach my profile to this node
    # ------------------------------------------------------------
    node.profile_id = me.id
    node.is_confirmed = True
    node.confirmed_at = _now()

    invite.status = "accepted"
    invite.responded_at = _now()

    # ------------------------------------------------------------
    # STEP 2: Find my existing confirmed node in ANOTHER ACTIVE tree
    # ------------------------------------------------------------
    my_existing_node = (
        db.query(FamilyTreeNode)
        .join(FamilyTree, FamilyTree.id == FamilyTreeNode.tree_id)
        .filter(
            FamilyTreeNode.profile_id == me.id,
            FamilyTreeNode.is_confirmed == True,
            FamilyTreeNode.tree_id != invite.tree_id,
            FamilyTree.is_archived == False,
        )
        .order_by(FamilyTree.id.desc())
        .first()
    )

    merged = False

    # ------------------------------------------------------------
    # STEP 3: Merge my old tree INTO the invite tree
    # ------------------------------------------------------------
    if my_existing_node:
        from_tree_id = my_existing_node.tree_id
        to_tree_id = invite.tree_id

        _execute_tree_merge(db, from_tree_id, to_tree_id)
        merged = True

    # ------------------------------------------------------------
    # DONE
    # No cleanup step needed!
    # Merge already collapses claimed nodes correctly.
    # ------------------------------------------------------------

    db.commit()

    return {
        "status": "accepted",
        "node_id": node.id,
        "tree_id": invite.tree_id,
        "merged": merged,
    }

@router.post("/invite/{invite_id}/decline")
def decline_invite(
    invite_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    invite = db.query(FamilyTreeInvite).filter(FamilyTreeInvite.id == invite_id).first()
    if not invite or invite.status != "pending":
        raise HTTPException(404, "Invite not found")

    me = get_current_user_profile(db, current_user.id)

    if invite.invited_profile_id and invite.invited_profile_id != me.id:
        raise HTTPException(403, "Not authorised to decline this invite")

    invite.status = "declined"
    invite.responded_at = _now()
    db.commit()
    return {"status": "declined"}
@router.post("/{tree_id}/node/{node_id}/unclaim")
def unclaim_node(
    tree_id: int,
    node_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    me = get_current_user_profile(db, current_user.id)

    # ------------------------------------------------------------
    # 1. Load the node being unclaimed
    # ------------------------------------------------------------
    node = db.query(FamilyTreeNode).filter(
        FamilyTreeNode.id == node_id,
        FamilyTreeNode.tree_id == tree_id,
        FamilyTreeNode.profile_id == me.id,
    ).first()

    if not node:
        raise HTTPException(404, "Node not found or not yours")

    # ------------------------------------------------------------
    # 2. Detach profile from this node
    # ------------------------------------------------------------
    node.profile_id = None
    node.is_confirmed = False
    node.confirmed_at = None

    # ------------------------------------------------------------
    # 3. Create a brand new personal tree
    # ------------------------------------------------------------
    new_tree = FamilyTree(
        name="My Tree",
        created_by_profile_id=me.id,
    )

    db.add(new_tree)
    db.commit()
    db.refresh(new_tree)

    # ------------------------------------------------------------
    # 4. Create a fresh confirmed "Me" node inside new tree
    # ------------------------------------------------------------
    my_node = FamilyTreeNode(
        tree_id=new_tree.id,
        profile_id=me.id,
        display_name=me.full_name or "Me",
        is_confirmed=True,
        confirmed_at=_now(),
    )

    db.add(my_node)
    db.commit()

    # ------------------------------------------------------------
    # 5. Return new tree id so Flutter can switch immediately
    # ------------------------------------------------------------
    return {
        "status": "ok",
        "new_tree_id": new_tree.id,
    }
# ============================================================
# Tree Merge
# ============================================================
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

def _execute_tree_merge(db: Session, from_tree_id: int, to_tree_id: int):
    """
    TRUE MERGE:
    - Use confirmed/claimed nodes with the same profile_id as join points.
    - Collapse duplicates (node-level).
    - Rewrite unions + parent-child links to canonical nodes.
    - Deduplicate unions after rewrite.
    - Move remaining records and archive from_tree.
    """

    if from_tree_id == to_tree_id:
        return

    # ----------------------------
    # 1) Find join points by profile_id
    # ----------------------------
    to_nodes = db.query(FamilyTreeNode).filter(FamilyTreeNode.tree_id == to_tree_id).all()
    from_nodes = db.query(FamilyTreeNode).filter(FamilyTreeNode.tree_id == from_tree_id).all()

    to_by_profile = {}
    for n in to_nodes:
        if n.profile_id:
            # prefer confirmed nodes as the canonical target
            existing = to_by_profile.get(n.profile_id)
            if not existing or (not existing.is_confirmed and n.is_confirmed):
                to_by_profile[n.profile_id] = n

    node_map = {}  # from_node_id -> to_node_id
    join_from_node_ids = set()

    for n in from_nodes:
        if n.profile_id and n.profile_id in to_by_profile:
            join_from_node_ids.add(n.id)
            node_map[n.id] = to_by_profile[n.profile_id].id

    # Helper for rewriting IDs
    def remap(node_id: int | None) -> int | None:
        if node_id is None:
            return None
        return node_map.get(node_id, node_id)

    # ----------------------------
    # 2) Move NON-join nodes into target tree
    # ----------------------------
    db.query(FamilyTreeNode).filter(
        FamilyTreeNode.tree_id == from_tree_id,
        ~FamilyTreeNode.id.in_(join_from_node_ids)
    ).update({"tree_id": to_tree_id}, synchronize_session=False)

    # We'll delete join nodes from from_tree after rewiring everything.

    # ----------------------------
    # 3) Move unions and rewrite partner ids through node_map
    # ----------------------------
    from_unions = db.query(FamilyUnion).filter(FamilyUnion.tree_id == from_tree_id).all()
    for u in from_unions:
        u.tree_id = to_tree_id
        u.partner_a_node_id = remap(u.partner_a_node_id)
        u.partner_b_node_id = remap(u.partner_b_node_id)

    # ----------------------------
    # 4) Move UnionChild links and rewrite node ids + union ids later
    # ----------------------------
    from_links = db.query(UnionChild).filter(UnionChild.tree_id == from_tree_id).all()
    for link in from_links:
        link.tree_id = to_tree_id
        link.child_node_id = remap(link.child_node_id)
        link.single_parent_id = remap(link.single_parent_id)

    db.flush()  # ensure IDs exist/updates applied before dedupe

    # ----------------------------
    # 5) Deduplicate unions (same couple) in to_tree
    # ----------------------------
    # Build existing union index in to_tree
    all_unions = db.query(FamilyUnion).filter(FamilyUnion.tree_id == to_tree_id).all()

    def union_key(a: int, b: int) -> tuple[int, int]:
        return (a, b) if a <= b else (b, a)

    union_index = {}
    for u in all_unions:
        if u.partner_a_node_id and u.partner_b_node_id:
            union_index[union_key(u.partner_a_node_id, u.partner_b_node_id)] = u.id

    # Now for unions that originated in from_tree, detect duplicates
    # (We can identify them because they were in from_unions list.)
    for u in from_unions:
        a = u.partner_a_node_id
        b = u.partner_b_node_id
        if not a or not b:
            continue

        key = union_key(a, b)
        canonical_union_id = union_index.get(key)

        # If canonical union exists but it's not this union, repoint children then delete dup
        if canonical_union_id and canonical_union_id != u.id:
            db.query(UnionChild).filter(
                UnionChild.tree_id == to_tree_id,
                UnionChild.union_id == u.id
            ).update({"union_id": canonical_union_id}, synchronize_session=False)

            db.delete(u)
        else:
            # ensure the union is indexed
            union_index[key] = u.id

    db.flush()

    # ----------------------------
    # 6) Delete the "join point" nodes from from_tree (now redundant)
    # ----------------------------
    if join_from_node_ids:
        db.query(FamilyTreeNode).filter(
            FamilyTreeNode.tree_id == from_tree_id,
            FamilyTreeNode.id.in_(join_from_node_ids)
        ).delete(synchronize_session=False)

    # ----------------------------
    # 7) Move invites across (tree-level)
    # ----------------------------
    db.query(FamilyTreeInvite).filter(
        FamilyTreeInvite.tree_id == from_tree_id
    ).update({"tree_id": to_tree_id}, synchronize_session=False)

    # ----------------------------
    # 8) Archive from_tree
    # ----------------------------
    from_tree = db.query(FamilyTree).filter(FamilyTree.id == from_tree_id).first()
    if from_tree:
        from_tree.is_archived = True
        from_tree.merged_into_tree_id = to_tree_id
        from_tree.archived_at = _now()

    db.commit()
