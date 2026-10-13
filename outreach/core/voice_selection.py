"""Explicit sender assignment; no arbitrary workspace fallback or implicit default."""
from outreach.core.workspace_scope import workspace_scope


def require_reference(profile: dict) -> None:
    if (not isinstance(profile.get('id'), str) or not profile['id'].strip()
            or type(profile.get('revision')) is not int or profile['revision'] < 1
            or not isinstance(profile.get('elevenlabs_voice_id'), str) or not profile['elevenlabs_voice_id'].strip()):
        raise ValueError('Voice selection needs a current profile and provider voice reference')


def assignment_ids(value: object) -> list[str]:
    if (not isinstance(value, list) or len(value) > 5
            or any(not isinstance(item, str) or not item.strip() or len(item) > 128 for item in value)
            or len(set(value)) != len(value)):
        raise ValueError('Voice sender assignments need explicit unique sender IDs')
    return value


async def selected_voice(db, workspace: str, sender: str) -> dict:
    if not isinstance(sender, str) or not sender.strip():
        raise ValueError('An explicit sender is required for voice selection')
    voices = await db.outreach_voices.find({**workspace_scope(workspace),
        'assigned_account_ids': sender}).limit(2).to_list(length=2)
    if len(voices) != 1:
        raise ValueError('Select exactly one voice for this sender in Voice Studio')
    voice = voices[0]
    require_reference(voice)
    if sender not in assignment_ids(voice.get('assigned_account_ids')):
        raise ValueError('Voice selection needs review in Voice Studio')
    return voice
