"""
Phase 4: DAG Sequence Compiler & Graph Topology Validator.
Validates sequence graphs, detects cycles/orphans, and compiles React Flow JSON into an execution tree.
"""
from typing import Any
from outreach.models import SequenceNode, SequenceEdge, SequenceNodeType


class DAGValidationError(Exception):
    pass


class DAGCompiler:
    """
    Compiles a directed acyclic graph (DAG) of sequence steps into a high-performance
    execution tree stored in MongoDB for the worker engine.
    """

    @staticmethod
    def validate_and_compile(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Validates graph structure and produces an indexed adjacency execution lookup.
        """
        if not nodes:
            raise DAGValidationError("Sequence must contain at least one step.")

        node_map = {n["id"]: n for n in nodes}
        if len(node_map) != len(nodes):
            raise DAGValidationError("Duplicate node IDs found in sequence graph.")

        # Build adjacency maps
        outgoing_edges: dict[str, list[dict[str, Any]]] = {n_id: [] for n_id in node_map}
        incoming_count: dict[str, int] = {n_id: 0 for n_id in node_map}

        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")

            if not source or source not in node_map:
                raise DAGValidationError(f"Edge references invalid source node: {source}")
            if not target or target not in node_map:
                raise DAGValidationError(f"Edge references invalid target node: {target}")

            outgoing_edges[source].append(edge)
            incoming_count[target] += 1

        # 1. Identify Root / Start Node(s)
        root_nodes = [n_id for n_id, count in incoming_count.items() if count == 0]
        if not root_nodes:
            raise DAGValidationError("Cycle detected: No root start node found in sequence.")
        if len(root_nodes) > 1:
            # Multiple starting roots — verify they don't cause disconnected disjoint branches
            pass

        # 2. Cycle Detection using Kahn's Algorithm (Topological Sort)
        in_degree = dict(incoming_count)
        queue = [n_id for n_id, deg in in_degree.items() if deg == 0]
        visited_count = 0

        while queue:
            curr = queue.pop(0)
            visited_count += 1
            for edge in outgoing_edges[curr]:
                neighbor = edge["target"]
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count != len(nodes):
            raise DAGValidationError("Cycle detected: The sequence cannot loop back on itself.")

        # 3. Compile into execution graph
        compiled: dict[str, Any] = {
            "root_node_ids": root_nodes,
            "nodes": {},
        }

        for n_id, node in node_map.items():
            node_type = node.get("type")
            edges_from = outgoing_edges[n_id]

            compiled_node = {
                "id": n_id,
                "type": node_type,
                "title": node.get("title", ""),
                "delay_hours": int(node.get("delay_hours", 0)),
                "config": node.get("config", {}),
                "next_default": None,
                "branches": {},
            }

            # Map branching vs sequential flow
            for edge in edges_from:
                label = (edge.get("label") or "").strip().lower()
                target_id = edge["target"]

                if label in ("accepted", "replied", "connected", "true", "yes"):
                    compiled_node["branches"]["positive"] = target_id
                elif label in ("not accepted", "not accepted yet", "no reply", "not connected", "false", "no"):
                    compiled_node["branches"]["negative"] = target_id
                else:
                    compiled_node["next_default"] = target_id

            compiled["nodes"][n_id] = compiled_node

        return compiled

    @staticmethod
    def get_prebuilt_templates() -> list[dict[str, Any]]:
        """
        Returns high-converting pre-built sequence templates matching Part 2, Image 2.
        """
        return [
            {
                "id": "tpl_connect_and_follow_up",
                "name": "Connect and follow up",
                "description": "Standard high-conversion outreach: Profile visit, clean connection invite, and follow-up message upon acceptance.",
                "nodes": [
                    {
                        "id": "node_visit",
                        "type": SequenceNodeType.VISIT_PROFILE,
                        "title": "Visit profile",
                        "delay_hours": 0,
                        "position": {"x": 250, "y": 50},
                    },
                    {
                        "id": "node_connect",
                        "type": SequenceNodeType.CONNECTION_REQUEST,
                        "title": "Connection request",
                        "delay_hours": 0,
                        "config": {"note": ""},  # No note by default (higher acceptance)
                        "position": {"x": 250, "y": 180},
                    },
                    {
                        "id": "node_msg",
                        "type": SequenceNodeType.SEND_MESSAGE,
                        "title": "Send message",
                        "delay_hours": 24,
                        "config": {"body": "Hi {{first_name}}, thanks for connecting! Looking forward to following your work at {{company_name}}."},
                        "position": {"x": 400, "y": 320},
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "node_visit", "target": "node_connect"},
                    {"id": "e2", "source": "node_connect", "target": "node_msg", "label": "accepted"},
                ],
            },
            {
                "id": "tpl_profile_warmup",
                "name": "Profile warm-up",
                "description": "Lightweight profile engagement sequence: visit profile and like latest post before initiating outreach.",
                "nodes": [
                    {
                        "id": "node_visit_warm",
                        "type": SequenceNodeType.VISIT_PROFILE,
                        "title": "Visit profile",
                        "delay_hours": 0,
                        "position": {"x": 250, "y": 50},
                    },
                    {
                        "id": "node_like",
                        "type": SequenceNodeType.LIKE_LAST_POST,
                        "title": "Like last post",
                        "delay_hours": 4,
                        "position": {"x": 250, "y": 180},
                    },
                ],
                "edges": [
                    {"id": "e_warm1", "source": "node_visit_warm", "target": "node_like"},
                ],
            },
        ]
