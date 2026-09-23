"""
Automated test suite for Phase 4: Visual DAG Sequence Engine & Compiler.
"""
import os
from cryptography.fernet import Fernet

if not os.environ.get("ENCRYPTION_KEY"):
    os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()

import pytest
from unittest.mock import AsyncMock
from outreach.core.dag_compiler import DAGCompiler, DAGValidationError
from outreach.models import SequenceNodeType
from outreach.api.sequences import (
    ValidateSequenceRequest,
    SaveSequenceRequest,
    get_sequence_templates,
    validate_sequence,
    save_campaign_sequence,
    get_campaign_sequence,
)


def test_dag_compiler_valid_sequence():
    """Verify linear sequence compiles with root node and default traversal pointers."""
    nodes = [
        {"id": "n1", "type": SequenceNodeType.VISIT_PROFILE, "title": "Visit", "delay_hours": 0},
        {"id": "n2", "type": SequenceNodeType.CONNECTION_REQUEST, "title": "Connect", "delay_hours": 0},
        {"id": "n3", "type": SequenceNodeType.SEND_MESSAGE, "title": "Message", "delay_hours": 24},
    ]
    edges = [
        {"id": "e1", "source": "n1", "target": "n2"},
        {"id": "e2", "source": "n2", "target": "n3", "label": "accepted"},
    ]

    compiled = DAGCompiler.validate_and_compile(nodes, edges)
    assert compiled["root_node_ids"] == ["n1"]
    assert compiled["nodes"]["n1"]["next_default"] == "n2"
    assert compiled["nodes"]["n2"]["branches"]["positive"] == "n3"


def test_dag_compiler_cycle_detection():
    """Verify cycle detection identifies infinite feedback loops."""
    nodes = [
        {"id": "a", "type": SequenceNodeType.VISIT_PROFILE},
        {"id": "b", "type": SequenceNodeType.SEND_MESSAGE},
        {"id": "c", "type": SequenceNodeType.LIKE_LAST_POST},
    ]
    # Circular loop: a -> b -> c -> a
    edges = [
        {"id": "e1", "source": "a", "target": "b"},
        {"id": "e2", "source": "b", "target": "c"},
        {"id": "e3", "source": "c", "target": "a"},
    ]

    with pytest.raises(DAGValidationError, match="Cycle detected"):
        DAGCompiler.validate_and_compile(nodes, edges)


def test_dag_compiler_invalid_edge_references():
    """Verify invalid node references are caught during compilation."""
    nodes = [{"id": "x", "type": SequenceNodeType.VISIT_PROFILE}]
    edges = [{"id": "e_bad", "source": "x", "target": "non_existent_node"}]

    with pytest.raises(DAGValidationError, match="invalid target node"):
        DAGCompiler.validate_and_compile(nodes, edges)


def test_prebuilt_templates_structure():
    """Verify prebuilt templates are syntactically valid and compile cleanly."""
    templates = DAGCompiler.get_prebuilt_templates()
    assert len(templates) >= 2
    for tpl in templates:
        compiled = DAGCompiler.validate_and_compile(tpl["nodes"], tpl["edges"])
        assert len(compiled["root_node_ids"]) >= 1


@pytest.mark.asyncio
async def test_sequence_api_endpoints():
    """Verify validation, save, and retrieval endpoints."""
    mock_db = AsyncMock()
    mock_db.outreach_sequences.find_one = AsyncMock(return_value=None)
    mock_db.outreach_sequences.update_one = AsyncMock()

    user = {"user_id": "u1"}

    # 1. Get templates
    tpls = await get_sequence_templates()
    assert len(tpls) >= 2

    # 2. Validate valid sequence
    val_req = ValidateSequenceRequest(
        nodes=[{"id": "n1", "type": "visit_profile"}],
        edges=[],
    )
    val_res = await validate_sequence(val_req)
    assert val_res["valid"] is True

    # 3. Save sequence
    save_req = SaveSequenceRequest(
        campaign_id="camp_xyz",
        nodes=[{"id": "n1", "type": "visit_profile"}],
        edges=[],
    )
    save_res = await save_campaign_sequence(req=save_req, current_user=user, db=mock_db)
    assert save_res["status"] == "success"
    mock_db.outreach_sequences.update_one.assert_awaited_once()

    # 4. Get default sequence when none exists
    seq_res = await get_campaign_sequence("camp_xyz", current_user=user, db=mock_db)
    assert seq_res["is_default"] is True


def test_dag_compiler_converging_branches():
    """Verify that multiple diverging branches can legally converge into a single target node without cycle errors."""
    # DAG:
    #      /--> step_b --\
    # step_a               --> step_d
    #      \--> step_c --/
    nodes = [
        {"id": "step_a", "type": SequenceNodeType.CONNECTION_REQUEST, "title": "Connect"},
        {"id": "step_b", "type": SequenceNodeType.SEND_MESSAGE, "title": "Accepted Msg"},
        {"id": "step_c", "type": SequenceNodeType.INMAIL, "title": "Not Accepted InMail"},
        {"id": "step_d", "type": SequenceNodeType.VISIT_PROFILE, "title": "Wrap-up Profile Visit"},
    ]
    edges = [
        {"id": "e_ab", "source": "step_a", "target": "step_b", "label": "accepted"},
        {"id": "e_ac", "source": "step_a", "target": "step_c", "label": "rejected"},
        {"id": "e_bd", "source": "step_b", "target": "step_d"},
        {"id": "e_cd", "source": "step_c", "target": "step_d"},
    ]

    compiled = DAGCompiler.validate_and_compile(nodes, edges)
    assert compiled["root_node_ids"] == ["step_a"]
    assert compiled["nodes"]["step_a"]["branches"]["positive"] == "step_b"
    assert compiled["nodes"]["step_a"]["branches"]["negative"] == "step_c"
    assert compiled["nodes"]["step_b"]["next_default"] == "step_d"
    assert compiled["nodes"]["step_c"]["next_default"] == "step_d"

    # Verify execution order processes step_a first, then step_b and step_c, and step_d last
    order = compiled["execution_order"]
    assert order.index("step_a") < order.index("step_b")
    assert order.index("step_a") < order.index("step_c")
    assert order.index("step_b") < order.index("step_d")
    assert order.index("step_c") < order.index("step_d")

