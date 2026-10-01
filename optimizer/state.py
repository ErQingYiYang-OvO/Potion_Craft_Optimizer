"""Exact state keys within one fixed BrewWorld, without rendered history.

This identifies states of the current engine model only. It does not certify
Unity scheduling, collision callbacks, or unmodelled persistent controllers.
"""
import json
from dataclasses import asdict


def future_state_key(session):
    state = {key:getattr(session,key) for key in (
        'base','position','rotation','health','minimum_health','heat','pending',
        'path_sections','ingredients_used','salts_used','effects','collected',
        'failed_reason','start_mode')}
    state['rotation_tween'] = asdict(session.rotation_tween) if session.rotation_tween else None
    return json.dumps(state,sort_keys=True,default=lambda value:sorted(value),separators=(',',':'))
