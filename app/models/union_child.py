from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey

from app.database import Base


class UnionChild(Base):
    """
    Links a child to either:
    - a union (two parents)
    OR
    - a single parent (unknown partner case)

    role supports biological/adoptive/step/guardian later.
    """

    __tablename__ = "union_children"

    id = Column(Integer, primary_key=True)

    tree_id = Column(
        Integer,
        ForeignKey("family_trees.id", ondelete="CASCADE"),
        nullable=False,
    )

    child_node_id = Column(
        Integer,
        ForeignKey("family_tree_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Child belongs to this couple
    union_id = Column(
        Integer,
        ForeignKey("family_unions.id", ondelete="CASCADE"),
        nullable=True,
    )

    # OR: child belongs to a single known parent
    single_parent_id = Column(
        Integer,
        ForeignKey("family_tree_nodes.id", ondelete="CASCADE"),
        nullable=True,
    )

    # biological / adoptive / step / guardian
    role = Column(String, default="biological", nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
