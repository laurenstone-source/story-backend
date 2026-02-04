from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey

from app.database import Base


class FamilyUnion(Base):
    """
    A partner/couple unit in a tree.
    Children belong to a union (when both parents are known).
    """

    __tablename__ = "family_unions"

    id = Column(Integer, primary_key=True)

    tree_id = Column(
        Integer,
        ForeignKey("family_trees.id", ondelete="CASCADE"),
        nullable=False,
    )

    partner_a_node_id = Column(
        Integer,
        ForeignKey("family_tree_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )

    partner_b_node_id = Column(
        Integer,
        ForeignKey("family_tree_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )

    # partner / married / divorced / separated (optional)
    status = Column(String, default="partner", nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
