"""Serve the local comparison GUI on localhost."""

import json
import sys
from collections import Counter
from dataclasses import asdict
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
sys.path.insert(0, str(PROJECT))
from engine.brew import BrewWorld, PotionSession, PotionFailed, distance  # noqa: E402
from engine.rotation import RotationTween

WORLD = BrewWorld()


def point(value):
    return (float(value["x"]), float(value["y"]))


def session_from_state(state):
    return PotionSession(
        WORLD, base=state.get("base", "Water"),
        position=point(state.get("pos", {"x": 0, "y": 0})),
        rotation=float(state.get("rotation", 0)), health=float(state.get("health", 1)),
        rotation_tween=RotationTween(**state["rotation_tween"]) if state.get("rotation_tween") else None,
        pending=[point(p) for p in state.get("pending", [])],
        ingredients_used=Counter(state.get("used", [])),
        effects=[tuple(e) for e in state.get("effects", [])],
        salts_used=Counter(state.get("salts", {})),
        collected=set(state.get("collected", [])),
        traveled=[[point(p) for p in trace] for trace in state.get("traveled", [])],
        path_sections=state.get("path_sections", []),
        heat=float(state.get("heat", 0)), failed_reason=state.get("failed_reason"),
        minimum_health=float(state.get("minimum_health", state.get("health", 1))),
        start_mode=state.get("start_mode", "base"),
        teleports=[{**event, "path": [point(p) for p in event["path"]],
                    "frames": [{**frame, "position": point(frame["position"])} for frame in event["frames"]]}
                   for event in state.get("teleports", [])],
    )


def session_state(session):
    def p(value):
        return {"x": value[0], "y": value[1]}
    return {"base": session.base, "pos": p(session.position),
            "rotation": session.rotation, "health": session.health,
            "target_rotation": session.target_rotation,
            "rotation_tween": asdict(session.rotation_tween) if session.rotation_tween else None,
            "minimum_health": session.minimum_health,
            "heat": session.heat, "failed_reason": session.failed_reason,
            "start_mode": session.start_mode,
            "pending": [p(v) for v in session.pending],
            "used": list(session.ingredients_used.elements()),
            "salts": dict(session.salts_used), "effects": session.effects,
            "collected": sorted(session.collected),
            "traveled": [[p(v) for v in trace] for trace in session.traveled],
            "remaining_length": session.remaining_length,
            "path_sections": session.path_sections,
            "teleports": [{**event, "path": [p(v) for v in event["path"]],
                           "frames": [{**frame, "position": p(frame["position"])} for frame in event["frames"]]}
                          for event in session.teleports],
            "nearest": session.nearest_effect(),
            "touching_vortex": (session.touching_vortex() or {}).get("name")}


def perform(session, action):
    kind = action["kind"]
    if kind == "inspect":
        return ""
    if kind == "vortex_demo":
        vortex = next(v for v in WORLD.vortices[session.base] if v["name"] == action["name"])
        session.__dict__.update(PotionSession(WORLD, base=session.base).__dict__)
        session.position = (vortex["entry"]["x"]+vortex["entry_radius"]*.4, vortex["entry"]["y"])
        session.heat = .8
        session.start_mode = "vortex_demo"
        session.add("Waterbloom", 0)
        return "机制观察场景：从漩涡旁起步，炉温 80%，预放一份 Waterbloom；此起点不能用于合法配方"
    if session.failed_reason:
        raise ValueError("本次药剂已失败，请撤销或清空后再操作")
    if kind == "add":
        session.add(action["name"], float(action["grind"]))
        return f"加入 {action['name']}，研磨 {float(action['grind'])*100:g}%"
    if kind == "stir":
        before = len(session.teleports)
        session.stir(float(action["fraction"]))
        if len(session.teleports) > before:
            return "搅拌触发晶体传送；传送完成，后续路径保留。生命值采用近似帧模拟"
        return f"搅拌剩余路径的 {float(action['fraction'])*100:g}%"
    if kind == "pour":
        session.pour(float(action["seconds"]), float(action["strength"]))
        return f"加基液 {action['seconds']} 秒，倒液强度 {float(action['strength'])*100:g}%"
    if kind == "center":
        session.pour_to_center()
        return "倒液至基液中心并恢复朝向，保留剩余路径"
    if kind == "salt":
        amount = float(action["amount"])
        if not 0 <= amount <= 10000:
            raise ValueError("Salt amount must be between 0 and 10000")
        salt = action["salt"]
        if salt in ("sun", "moon"):
            deferred = action.get("deferred", False)
            if not isinstance(deferred, bool):
                raise ValueError("deferred must be a boolean")
            session.rotate_salt(salt, amount, deferred=deferred)
            if deferred:
                return f"加入旋转盐 {amount:g} 单位；目标朝向已更新，动画随后续动作时间推进"
        elif salt == "life":
            session.life_salt(amount)
        elif salt == "void":
            session.void_salt(amount)
        elif salt == "philosopher":
            session.philosophers_salt(amount)
            return f"加入贤者之盐 {amount:g} 单位（同时溶解并等待生效，帧时序近似）"
        else:
            raise ValueError("Unknown salt")
        return f"加入 {dict(sun='太阳盐', moon='月亮盐', life='生命盐', void='虚无盐')[salt]} {amount:g} 单位"
    if kind in ("heat", "pump", "wait"):
        before = len(session.teleports)
        if kind == "wait":
            session.wait(float(action["seconds"]))
            message = f"等待 {action['seconds']} 秒，继续冷却与漩涡运动"
        else:
            angle, seconds = (60, .5) if kind == "heat" else (float(action["angle"]), float(action["seconds"]))
            session.pump_bellows(angle, seconds)
            message = f"累计鼓风下压 {angle:g}°，持续 {seconds:g} 秒"
        if len(session.teleports) > before:
            message += "；输入在漩涡传送开始时结束，等待传送完成，保留已有路径"
        return message
    raise ValueError(f"Unknown action: {kind}")


def replay(base, operations):
    if base not in WORLD.bases or not isinstance(operations, list) or len(operations) > 2000:
        raise ValueError("Invalid replay base or operation list")
    session = PotionSession(WORLD, base=base)
    messages, processed, failure = [], [], None
    for action in operations:
        if not isinstance(action, dict):
            raise ValueError("Each replay operation must be an object")
        try:
            message = perform(session, action)
        except PotionFailed as error:
            message, failure = f"药剂失败：{error}", str(error)
        processed.append(action)
        if message:
            messages.append(message)
        if failure:
            break
    return {"state": session_state(session), "steps": messages, "operations": processed, "failure": failure}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def translate_path(self, path):
        path = unquote(urlparse(path).path)
        if path.startswith(("/data/", "/result/")):
            target = (PROJECT / path.lstrip("/")).resolve()
            allowed = PROJECT / ("data" if path.startswith("/data/") else "result")
            if target.is_relative_to(allowed):
                return str(target)
            return str(ROOT / "__not_found__")
        return super().translate_path(path)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_POST(self):
        if self.path not in ("/api/action", "/api/replay"):
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4_000_000:
                raise ValueError("Invalid request size")
            body = json.loads(self.rfile.read(length))
            if self.path == "/api/replay":
                output = replay(body["base"], body["operations"])
            else:
                session = session_from_state(body["state"])
                try:
                    message = perform(session, body["action"])
                    output = {"state": session_state(session), "message": message}
                except PotionFailed as error:
                    output = {"state": session_state(session), "message": f"药剂失败：{error}", "failure": str(error)}
            code = 200
        except (ValueError, KeyError, TypeError, OverflowError, StopIteration, NotImplementedError, RuntimeError) as error:
            output, code = {"error": str(error)}, 400
        encoded = json.dumps(output, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    print("Potion Craft playground: http://127.0.0.1:8765", flush=True)
    server.serve_forever()
