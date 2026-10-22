"""
Phase 4: DAG Sequence Compiler & Graph Topology Validator.
Validates sequence graphs, detects cycles/orphans, and compiles React Flow JSON into an execution tree.
"""
import logging
logger = logging.getLogger(__name__)
import re
from typing import Any
from outreach.models import SequenceNodeType
from outreach.core.sequence_contract import DAGValidationError, graph_envelope, branch_kind, MAX_RENDER_CHARS


_TEMPLATE_TAG_RE = re.compile(
    r"\{\{\s*([A-Za-z_][A-Za-z0-9_]{0,99})(?:\s*\|\s*(?:\"([^\"{}]{0,200})\"|'([^'{}]{0,200})'|([^|{}]{1,200}?)))?\s*\}\}"
)

GUARANTEED_LINKEDIN_VARIABLES = ("first_name", "last_name", "location")


def find_missing_profile_variables(template_str: str, lead: dict[str, Any]) -> list[str]:
    """
    Returns variable names referenced in `template_str` (without an inline `| "fallback"`)
    that are missing or empty on `lead`.
    """
    if not isinstance(template_str, str) or not template_str.strip():
        return []
    custom_variables = lead.get("custom_variables") if isinstance(lead.get("custom_variables"), dict) else {}

    def _has_val(*keys: str) -> bool:
        for k in keys:
            v = lead.get(k)
            if v is not None and str(v).strip():
                return True
            cv = custom_variables.get(k)
            if cv is not None and str(cv).strip():
                return True
        return False

    alias_map: dict[str, tuple[str, ...]] = {
        "first_name": ("first_name",),
        "last_name": ("last_name",),
        "full_name": ("full_name", "first_name", "last_name"),
        "headline": ("headline",),
        "company_name": ("company_name", "company"),
        "company": ("company_name", "company"),
        "job_title": ("job_title", "position"),
        "position": ("job_title", "position"),
        "industry": ("industry",),
        "location_raw": ("location_raw", "location"),
        "location": ("location_raw", "location"),
        "country": ("country", "country_code"),
        "connections_count": ("connections_count", "number_of_connections", "connections"),
        "number_of_connections": ("connections_count", "number_of_connections", "connections"),
        "top_skill": ("top_skill", "skills"),
        "company_followed": ("company_followed", "followed_company"),
        "company_location": ("company_location", "hq_location"),
        "summary": ("summary", "about", "bio"),
        "school": ("university_name", "school", "education", "university"),
        "university_name": ("university_name", "school", "education", "university"),
        "university": ("university_name", "school", "education", "university"),
        "profile_type": ("profile_type", "is_open_profile", "is_premium"),
        "years_in_company": ("years_in_company", "company_tenure"),
        "years_in_role": ("years_in_role", "role_tenure"),
        "mutual_connections": ("mutual_connections", "shared_connections"),
    }

    missing: list[str] = []
    for match in _TEMPLATE_TAG_RE.finditer(template_str):
        var_name = match.group(1)
        inline_fallback = next(
            (g.strip() if idx == 4 and g is not None else g for idx, g in enumerate(match.groups()[1:], start=2) if g is not None),
            None,
        )
        if inline_fallback is not None and str(inline_fallback).strip():
            continue
        keys = alias_map.get(var_name, (var_name,))
        if var_name == "profile_type":
            if lead.get("is_open_profile") is True or lead.get("is_premium") is True or _has_val("profile_type"):
                continue
        elif _has_val(*keys):
            continue
        if var_name not in missing:
            missing.append(var_name)
    return missing


def resolve_step_message_with_alternative(
    primary_template: str,
    alternative_template: str | None,
    lead: dict[str, Any],
    *,
    strict_missing_check: bool = False,
) -> dict[str, Any]:
    """
    Resolves a sequence step message with Dripify-style Alternative Message fallback:
    - Checks if any profile variable in `primary_template` (without an inline fallback) is missing on `lead`.
    - If missing and `alternative_template` is provided, renders `alternative_template` and sets `used_alternative=True`.
    - If missing and no `alternative_template` is provided, returns `missing_variables` so callers can either
      fail with `missing_profile_variable` (when `strict_missing_check=True` or optional variables are missing)
      or use default interpolation.
    """
    primary_str = primary_template if isinstance(primary_template, str) else ""
    alt_str = (alternative_template or "").strip() if isinstance(alternative_template, str) else ""
    missing_primary = find_missing_profile_variables(primary_str, lead)

    if missing_primary and alt_str:
        missing_alt = find_missing_profile_variables(alt_str, lead)
        rendered_alt = interpolate_template(alt_str, lead)
        return {
            "text": rendered_alt,
            "used_alternative": True,
            "missing_variables": missing_primary,
            "missing_alternative_variables": missing_alt,
            "failed_missing_variable": bool(strict_missing_check and missing_alt),
        }

    # Check if any non-default variable (not first_name/company_name which have legacy defaults unless strict) is missing
    non_legacy_missing = [v for v in missing_primary if v not in ("first_name", "company_name", "company", "profile_type")]
    rendered_primary = interpolate_template(primary_str, lead) if primary_str else ""
    has_unreplaced_tokens = "{{" in rendered_primary or "}}" in rendered_primary
    failed = bool(
        has_unreplaced_tokens
        or (strict_missing_check and missing_primary)
        or (non_legacy_missing and not alt_str)
    )
    return {
        "text": rendered_primary,
        "used_alternative": False,
        "missing_variables": missing_primary,
        "missing_alternative_variables": [],
        "failed_missing_variable": failed,
    }


def interpolate_template(template_str: str, lead: dict[str, Any]) -> str:
    """Replaces dynamic tags like {{first_name}}, {{top_skill | "leadership"}}, and {{company_name}} with lead attributes."""
    first_name = lead.get("first_name") or "there"
    last_name = lead.get("last_name") or ""
    company = lead.get("company_name") or lead.get("company") or "your company"
    title = lead.get("job_title") or lead.get("position") or ""
    custom_variables = lead.get("custom_variables") or {}
    if not isinstance(custom_variables, dict):
        raise DAGValidationError("Message variables need review.")

    def _str_field(key: str, *aliases: str) -> str:
        for k in (key, *aliases):
            val = lead.get(k)
            if val is not None and str(val).strip():
                return str(val).strip()
            cval = custom_variables.get(k)
            if cval is not None and str(cval).strip():
                return str(cval).strip()
        return ""

    location_val = lead.get("location_raw") or lead.get("location") or custom_variables.get("location") or ""
    connections_val = _str_field("connections_count", "number_of_connections", "connections")
    school_val = _str_field("university_name", "school", "education", "university")
    profile_type_val = (
        "Open Profile"
        if lead.get("is_open_profile") is True
        else "Premium"
        if lead.get("is_premium") is True
        else (_str_field("profile_type") or "Standard")
    )
    built_in_variables = {
        "first_name": first_name,
        "last_name": last_name,
        "full_name": " ".join(part for part in (first_name if lead.get("first_name") else "", last_name) if part).strip() or first_name,
        "headline": lead.get("headline") or custom_variables.get("headline") or (f"{title} at {company}" if title else company),
        "company_name": company,
        "company": company,
        "job_title": title,
        "position": title,
        "industry": _str_field("industry"),
        "location_raw": location_val,
        "location": location_val,
        "country": _str_field("country", "country_code"),
        "connections_count": connections_val,
        "number_of_connections": connections_val,
        "top_skill": _str_field("top_skill", "skills"),
        "company_followed": _str_field("company_followed", "followed_company"),
        "company_location": _str_field("company_location", "hq_location"),
        "summary": _str_field("summary", "about", "bio"),
        "school": school_val,
        "university_name": school_val,
        "university": school_val,
        "profile_type": profile_type_val,
        "years_in_company": _str_field("years_in_company", "company_tenure"),
        "years_in_role": _str_field("years_in_role", "role_tenure"),
        "mutual_connections": _str_field("mutual_connections", "shared_connections"),
    }

    if not isinstance(template_str, str) or not isinstance(custom_variables, dict):
        raise DAGValidationError("Message template and variables need review.")
    values = {**custom_variables, **built_in_variables}
    parts, total, cursor = [], 0, 0
    # Resolve once. Values cannot recursively introduce more substitutions.
    for match in _TEMPLATE_TAG_RE.finditer(template_str):
        prefix = template_str[cursor:match.start()]
        var_name = match.group(1)
        fallback = next((g.strip() if idx == 4 and g is not None else g for idx, g in enumerate(match.groups()[1:], start=2) if g is not None), None)
        if var_name in values:
            raw_val = str(values[var_name])
            replacement = raw_val if raw_val.strip() or fallback is None else fallback
        elif fallback is not None:
            replacement = fallback
        else:
            replacement = match.group()
        total += len(prefix) + len(replacement)
        if total > MAX_RENDER_CHARS:
            raise DAGValidationError("Rendered message exceeds the 10,000-character review bound.")
        parts.extend((prefix, replacement)); cursor = match.end()
    suffix = template_str[cursor:]
    if total + len(suffix) > MAX_RENDER_CHARS:
        raise DAGValidationError("Rendered message exceeds the 10,000-character review bound.")
    return ''.join((*parts, suffix))


def select_step_variant(
    node: dict[str, Any],
    lead: dict[str, Any] | None = None,
) -> tuple[str | None, dict[str, Any]]:
    """
    Deterministically selects an A/B/C message variant for a lead at a sequence step.
    Returns (variant_id, merged_config). If no variants exist, returns (None, config).
    """
    import hashlib

    base_config = dict(node.get("config") or {})
    variants = base_config.get("variants")
    if not isinstance(variants, list) or not variants:
        return None, base_config

    valid_variants = [v for v in variants if isinstance(v, dict) and isinstance(v.get("id"), str) and v["id"].strip()]
    if not valid_variants:
        return None, base_config

    node_id = str(node.get("id") or "step")
    lead_obj = lead or {}
    assigned_map = lead_obj.get("ab_variants_assigned")
    if isinstance(assigned_map, dict) and isinstance(assigned_map.get(node_id), str):
        forced_id = assigned_map[node_id].strip()
        for v in valid_variants:
            if v["id"].strip() == forced_id:
                merged = {**base_config, **{k: val for k, val in v.items() if k != "id"}}
                return forced_id, merged

    lead_key = str(lead_obj.get("id") or lead_obj.get("linkedin_url") or "sample")
    digest = hashlib.sha256(f"{lead_key}:{node_id}".encode("utf-8")).digest()
    chosen = valid_variants[int.from_bytes(digest[:4], "big") % len(valid_variants)]
    variant_id = chosen["id"].strip()
    merged = {**base_config, **{k: val for k, val in chosen.items() if k != "id"}}
    return variant_id, merged


def contains_ai_prompt_token(value: Any) -> bool:
    """Detect prompt-library tokens that the live sequence runner cannot generate."""
    if isinstance(value, str):
        return "✨ [" in value
    if isinstance(value, dict):
        return any(contains_ai_prompt_token(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(contains_ai_prompt_token(item) for item in value)
    return False


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
        graph_envelope(nodes, edges)
        for node in nodes:
            try:
                SequenceNodeType(node["type"])
            except ValueError:
                raise DAGValidationError(f"Invalid step type for node: {node['id']}") from None

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
            raise DAGValidationError("Sequence contains disconnected steps. Connect every step to the start flow.")

        # 2. Cycle Detection using Kahn's Algorithm (Topological Sort)
        in_degree = dict(incoming_count)
        queue = [n_id for n_id, deg in in_degree.items() if deg == 0]
        visited_count = 0
        execution_order: list[str] = []

        while queue:
            curr = queue.pop(0)
            execution_order.append(curr)
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
            "execution_order": execution_order,
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

            branch_targets: set[str] = set()
            for edge in edges_from:
                label = edge.get("label")
                handle = edge.get("sourceHandle")
                label_kind = branch_kind(node_type, label) if label not in (None, '') else None
                handle_kind = branch_kind(node_type, handle) if handle not in (None, '') else None
                if label_kind and handle_kind and label_kind != handle_kind:
                    raise DAGValidationError(f"Step {n_id} has conflicting display and handle branch labels.")
                selected = handle_kind or label_kind or branch_kind(node_type, None)
                if selected in branch_targets:
                    raise DAGValidationError(f"Step {n_id} has more than one {selected} next step.")
                branch_targets.add(selected)
                if selected == "default":
                    compiled_node["next_default"] = edge["target"]
                else:
                    compiled_node["branches"][selected] = edge["target"]
            if "default" in branch_targets and len(branch_targets) > 1:
                raise DAGValidationError(f"Step {n_id} mixes default and conditional successors.")

            compiled["nodes"][n_id] = compiled_node

        return compiled

    @staticmethod
    def get_prebuilt_templates() -> list[dict[str, Any]]:
        """
        Returns pre-built sequence templates matching media_1790104784825.png,
        media_1790104824235.png, and media_1790104866987.png.
        """
        return [
            {
                "id": "tpl_connect_and_follow_up",
                "name": "Connect and follow up",
                "description": "Clean connection invite with no note, and follow-up message 1 day after acceptance.",
                "nodes": [
                    {
                        "id": "step_connect_root",
                        "type": SequenceNodeType.CONNECTION_REQUEST,
                        "title": "Connection request",
                        "subtitle": "Send a connection request",
                        "delay_hours": 0,
                        "config": {"note": ""},
                        "position": {"x": 250, "y": 50},
                    },
                    {
                        "id": "step_msg_followup",
                        "type": SequenceNodeType.SEND_MESSAGE,
                        "title": "Send message",
                        "subtitle": "Hi {{first_name}}, thanks for...",
                        "delay_hours": 24,
                        "config": {
                            "body": "Hi {{first_name}}, thanks for connecting! Looking forward to following your work at {{company_name}}.",
                        },
                        "position": {"x": 400, "y": 200},
                    },
                ],
                "edges": [
                    {"id": "e_conn_to_msg", "source": "step_connect_root", "target": "step_msg_followup", "label": "accepted"},
                ],
                "tree": [
                    {
                        "id": "step_connect_root",
                        "type": "connection_request",
                        "title": "Connection request",
                        "subtitle": "Send a connection request",
                        "delay_days": 0,
                        "config": {"note": ""},
                        "branches": {
                            "left": {
                                "condition": "not accepted yet",
                                "type": "danger",
                                "steps": [],
                                "endsHere": True,
                            },
                            "right": {
                                "condition": "accepted",
                                "type": "success",
                                "steps": [
                                    {
                                        "id": "step_msg_followup",
                                        "type": "send_message",
                                        "title": "Send message",
                                        "subtitle": "Hi {{first_name}}, thanks for...",
                                        "delay_days": 1,
                                        "config": {
                                            "body": "Hi {{first_name}}, thanks for connecting! Looking forward to following your work at {{company_name}}.",
                                        },
                                        "branches": {
                                            "left": {"condition": "no reply", "type": "danger", "steps": [], "endsHere": True},
                                            "right": {"condition": "replied", "type": "success", "steps": [], "endsHere": True},
                                        },
                                    }
                                ],
                            },
                        },
                    }
                ],
            },
            {
                "id": "tpl_profile_warmup",
                "name": "Profile warm-up",
                "description": "Multi-touch warm-up sequence: View profile and like recent post before sending a connection invite and welcome message.",
                "nodes": [
                    {
                        "id": "step_warmup_visit",
                        "type": SequenceNodeType.VISIT_PROFILE,
                        "title": "Visit profile",
                        "subtitle": "Visit lead's profile",
                        "delay_hours": 0,
                        "config": {"dwell_mode": "realistic", "skip_if_visited": True},
                        "position": {"x": 250, "y": 50},
                    },
                    {
                        "id": "step_warmup_like",
                        "type": SequenceNodeType.LIKE_LAST_POST,
                        "title": "Like last post",
                        "subtitle": "Like most recent activity",
                        "delay_hours": 24,
                        "config": {"max_post_age_days": 30, "skip_if_no_posts": True},
                        "position": {"x": 250, "y": 180},
                    },
                    {
                        "id": "step_warmup_connect",
                        "type": SequenceNodeType.CONNECTION_REQUEST,
                        "title": "Connection request",
                        "subtitle": "Send a connection request",
                        "delay_hours": 24,
                        "config": {"note": ""},
                        "position": {"x": 250, "y": 310},
                    },
                    {
                        "id": "step_warmup_msg",
                        "type": SequenceNodeType.SEND_MESSAGE,
                        "title": "Send message",
                        "subtitle": "Hi {{first_name}}, thanks for...",
                        "delay_hours": 24,
                        "config": {
                            "body": "Hi {{first_name}}, thanks for connecting! Looking forward to following your work at {{company_name}}.",
                        },
                        "position": {"x": 400, "y": 440},
                    },
                ],
                "edges": [
                    {"id": "e_warmup_1", "source": "step_warmup_visit", "target": "step_warmup_like"},
                    {"id": "e_warmup_2", "source": "step_warmup_like", "target": "step_warmup_connect"},
                    {"id": "e_warmup_3", "source": "step_warmup_connect", "target": "step_warmup_msg", "label": "accepted"},
                ],
                "tree": [
                    {
                        "id": "step_warmup_visit",
                        "type": "visit_profile",
                        "title": "Visit profile",
                        "subtitle": "Visit lead's profile",
                        "delay_days": 0,
                        "config": {"dwell_mode": "realistic", "skip_if_visited": True},
                    },
                    {
                        "id": "step_warmup_like",
                        "type": "like_last_post",
                        "title": "Like last post",
                        "subtitle": "Like most recent activity",
                        "delay_days": 1,
                        "config": {"max_post_age_days": 30, "skip_if_no_posts": True},
                    },
                    {
                        "id": "step_warmup_connect",
                        "type": "connection_request",
                        "title": "Connection request",
                        "subtitle": "Send a connection request",
                        "delay_days": 1,
                        "config": {"note": ""},
                        "branches": {
                            "left": {
                                "condition": "not accepted yet",
                                "type": "danger",
                                "steps": [],
                                "endsHere": True,
                            },
                            "right": {
                                "condition": "accepted",
                                "type": "success",
                                "steps": [
                                    {
                                        "id": "step_warmup_msg",
                                        "type": "send_message",
                                        "title": "Send message",
                                        "subtitle": "Hi {{first_name}}, thanks for...",
                                        "delay_days": 1,
                                        "config": {
                                            "body": "Hi {{first_name}}, thanks for connecting! Looking forward to following your work at {{company_name}}.",
                                        },
                                        "branches": {
                                            "left": {"condition": "no reply", "type": "danger", "steps": [], "endsHere": True},
                                            "right": {"condition": "replied", "type": "success", "steps": [], "endsHere": True},
                                        },
                                    }
                                ],
                            },
                        },
                    },
                ],
            },
            {
                "id": "tpl_voice_note_outreach",
                "name": "Voice note outreach",
                "description": "Profile visit, clean invite, and personalized voice note upon acceptance.",
                "nodes": [
                    {
                        "id": "step_vn_visit",
                        "type": SequenceNodeType.VISIT_PROFILE,
                        "title": "Visit profile",
                        "subtitle": "Visit lead's profile",
                        "delay_hours": 0,
                        "config": {},
                        "position": {"x": 250, "y": 50},
                    },
                    {
                        "id": "step_vn_connect",
                        "type": SequenceNodeType.CONNECTION_REQUEST,
                        "title": "Connection request",
                        "subtitle": "Send a connection request",
                        "delay_hours": 24,
                        "config": {"note": ""},
                        "position": {"x": 250, "y": 180},
                    },
                    {
                        "id": "step_vn_voice",
                        "type": SequenceNodeType.VOICE_NOTE,
                        "title": "Voice note",
                        "subtitle": "Personalized AI cloned voice bubble",
                        "delay_hours": 24,
                        "config": {
                            "script": "Hey {{first_name}}, saw your work at {{company_name}} and wanted to send a quick voice note to introduce myself!",
                            "fallback": "Hi {{first_name}}, wanted to reach out and say hello! Excited to connect.",
                        },
                        "position": {"x": 400, "y": 320},
                    },
                    {
                        "id": "step_vn_msg",
                        "type": SequenceNodeType.SEND_MESSAGE,
                        "title": "Send message",
                        "subtitle": "Following up on voice note",
                        "delay_hours": 48,
                        "config": {
                            "body": "Hey {{first_name}}, following up on my quick voice note—would love to hear your thoughts when you have a moment!",
                        },
                        "position": {"x": 300, "y": 460},
                    },
                ],
                "edges": [
                    {"id": "e_vn_1", "source": "step_vn_visit", "target": "step_vn_connect"},
                    {"id": "e_vn_2", "source": "step_vn_connect", "target": "step_vn_voice", "label": "accepted"},
                    {"id": "e_vn_3", "source": "step_vn_voice", "target": "step_vn_msg", "label": "no reply"},
                ],
                "tree": [
                    {
                        "id": "step_vn_visit",
                        "type": "visit_profile",
                        "title": "Visit profile",
                        "subtitle": "Visit lead's profile",
                        "delay_days": 0,
                        "config": {},
                    },
                    {
                        "id": "step_vn_connect",
                        "type": "connection_request",
                        "title": "Connection request",
                        "subtitle": "Send a connection request",
                        "delay_days": 1,
                        "config": {"note": ""},
                        "branches": {
                            "left": {
                                "condition": "not accepted yet",
                                "type": "danger",
                                "steps": [],
                                "endsHere": True,
                            },
                            "right": {
                                "condition": "accepted",
                                "type": "success",
                                "steps": [
                                    {
                                        "id": "step_vn_voice",
                                        "type": "voice_note",
                                        "title": "Voice note",
                                        "subtitle": "Personalized AI cloned voice bubble",
                                        "delay_days": 1,
                                        "config": {
                                            "script": "Hey {{first_name}}, saw your work at {{company_name}} and wanted to send a quick voice note to introduce myself!",
                                            "fallback": "Hi {{first_name}}, wanted to reach out and say hello! Excited to connect.",
                                        },
                                        "branches": {
                                            "left": {
                                                "condition": "no reply",
                                                "type": "danger",
                                                "steps": [
                                                    {
                                                        "id": "step_vn_msg",
                                                        "type": "send_message",
                                                        "title": "Send message",
                                                        "subtitle": "Following up on voice note",
                                                        "delay_days": 2,
                                                        "config": {
                                                            "body": "Hey {{first_name}}, following up on my quick voice note—would love to hear your thoughts when you have a moment!",
                                                        },
                                                        "branches": {
                                                            "left": {"condition": "no reply", "type": "danger", "steps": [], "endsHere": True},
                                                            "right": {"condition": "replied", "type": "success", "steps": [], "endsHere": True},
                                                        },
                                                    }
                                                ],
                                            },
                                            "right": {
                                                "condition": "replied",
                                                "type": "success",
                                                "steps": [],
                                                "endsHere": True,
                                            },
                                        },
                                    }
                                ],
                            },
                        },
                    },
                ],
            },
            {
                "id": "tpl_multitouch_inmail",
                "name": "Multi-touch InMail & engage",
                "description": "Engage via follow and post like before dispatching targeted InMail directly to decision makers.",
                "nodes": [
                    {
                        "id": "step_inmail_follow",
                        "type": SequenceNodeType.FOLLOW,
                        "title": "Follow",
                        "subtitle": "Follow lead's profile",
                        "delay_hours": 0,
                        "config": {},
                        "position": {"x": 250, "y": 50},
                    },
                    {
                        "id": "step_inmail_like",
                        "type": SequenceNodeType.LIKE_LAST_POST,
                        "title": "Like last post",
                        "subtitle": "Like most recent activity",
                        "delay_hours": 24,
                        "config": {},
                        "position": {"x": 250, "y": 180},
                    },
                    {
                        "id": "step_inmail_send",
                        "type": SequenceNodeType.INMAIL,
                        "title": "InMail",
                        "subtitle": "Send message to 2nd/3rd degree lead",
                        "delay_hours": 24,
                        "config": {
                            "subject": "Quick question regarding {{company_name}}",
                            "body": "Hi {{first_name}}, came across your profile and noticed your focus at {{company_name}}. Would love to share a quick perspective if you are open to it!",
                            "message": "Hi {{first_name}}, came across your profile and noticed your focus at {{company_name}}. Would love to share a quick perspective if you are open to it!",
                        },
                        "position": {"x": 250, "y": 320},
                    },
                ],
                "edges": [
                    {"id": "e_inmail_1", "source": "step_inmail_follow", "target": "step_inmail_like"},
                    {"id": "e_inmail_2", "source": "step_inmail_like", "target": "step_inmail_send"},
                ],
                "tree": [
                    {
                        "id": "step_inmail_follow",
                        "type": "follow",
                        "title": "Follow",
                        "subtitle": "Follow lead's profile",
                        "delay_days": 0,
                        "config": {},
                    },
                    {
                        "id": "step_inmail_like",
                        "type": "like_last_post",
                        "title": "Like last post",
                        "subtitle": "Like most recent activity",
                        "delay_days": 1,
                        "config": {},
                    },
                    {
                        "id": "step_inmail_send",
                        "type": "inmail",
                        "title": "InMail",
                        "subtitle": "Send message to 2nd/3rd degree lead",
                        "delay_days": 1,
                        "config": {
                            "subject": "Quick question regarding {{company_name}}",
                            "body": "Hi {{first_name}}, came across your profile and noticed your focus at {{company_name}}. Would love to share a quick perspective if you are open to it!",
                            "message": "Hi {{first_name}}, came across your profile and noticed your focus at {{company_name}}. Would love to share a quick perspective if you are open to it!",
                        },
                        "branches": {
                            "left": {"condition": "no reply", "type": "danger", "steps": [], "endsHere": True},
                            "right": {"condition": "replied", "type": "success", "steps": [], "endsHere": True},
                        },
                    },
                ],
            },
        ]
