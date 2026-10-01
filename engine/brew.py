"""Programmatic Potion Craft 2.0.2 brewing geometry sandbox.

This module reads extracted game data. It exposes path, collision, and effect
queries for optimization experiments. Crystals, vortices, heat and forcefields
are supported with approximate frame/collider/rotation scheduling.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from engine.rotation import RotationTween


DATA = Path(__file__).resolve().parent.parent / "data"
LEVEL = {"Water": 6, "Oil": 7, "Wine": 8}


def read(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def xy(p):
    return (p["x"], p["y"])


def rotate_about(point, pivot, degrees):
    angle = math.radians(degrees)
    dx, dy = point[0] - pivot[0], point[1] - pivot[1]
    return (pivot[0] + dx * math.cos(angle) - dy * math.sin(angle),
            pivot[1] + dx * math.sin(angle) + dy * math.cos(angle))


def curve_value(curve, time):
    """Unity AnimationCurve interpolation, including weighted Bezier tangents."""
    keys = curve["m_Curve"]
    if time <= keys[0]["time"]:
        return keys[0]["value"]
    if time >= keys[-1]["time"]:
        return keys[-1]["value"]
    for a, b in zip(keys, keys[1:]):
        if a["time"] <= time <= b["time"]:
            duration = b["time"] - a["time"]
            t = (time - a["time"]) / duration
            if not math.isfinite(a["outSlope"]) or not math.isfinite(b["inSlope"]):
                return a["value"]
            if a["weightedMode"] & 2 or b["weightedMode"] & 1:
                outgoing = a["outWeight"] if a["weightedMode"] & 2 else 1/3
                incoming = b["inWeight"] if b["weightedMode"] & 1 else 1/3
                low, high = 0.0, 1.0
                for _ in range(52):
                    u = (low + high) / 2
                    x = 3*(1-u)**2*u*outgoing + 3*(1-u)*u*u*(1-incoming) + u**3
                    if x < t:
                        low = u
                    else:
                        high = u
                u = (low + high) / 2
                y1 = a["value"] + a["outSlope"] * duration * outgoing
                y2 = b["value"] - b["inSlope"] * duration * incoming
                return ((1-u)**3*a["value"] + 3*(1-u)**2*u*y1
                        + 3*(1-u)*u*u*y2 + u**3*b["value"])
            return ((2*t**3 - 3*t**2 + 1) * a["value"]
                    + (t**3 - 2*t**2 + t) * duration * a["outSlope"]
                    + (-2*t**3 + 3*t**2) * b["value"]
                    + (t**3 - t**2) * duration * b["inSlope"])
    raise ValueError("Invalid curve")


def bezier(curve, t):
    p0, p1, p2, p3 = (xy(curve[k]) for k in ("PFirst", "P1", "P2", "PLast"))
    u = 1 - t
    return (u*u*u*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t*t*t*p3[0],
            u*u*u*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t*t*t*p3[1])


def sampled_path(curves, spacing):
    """Port of EvenlySpacedPointsPath.CalculateEvenlySpacedPoints."""
    points = [xy(curves[0]["PFirst"])]
    previous = points[0]
    since_last = 0.0
    for curve in curves:
        divisions = math.ceil(10 * curve["_length"])
        for j in range(divisions + 1):
            point = bezier(curve, j / divisions)
            since_last += distance(previous, point)
            while since_last >= spacing:
                since_last -= spacing
                dx, dy = previous[0] - point[0], previous[1] - point[1]
                norm = math.hypot(dx, dy) or 1.0
                next_point = (point[0] + dx / norm * since_last,
                              point[1] + dy / norm * since_last)
                points.append(next_point)
                previous = next_point
            previous = point
    if since_last > 0:
        points.append(xy(curves[-1]["PLast"]))
    return points


def cut_path(points, fraction):
    if fraction >= 1:
        return points
    total = sum(distance(a, b) for a, b in zip(points, points[1:]))
    target = total * fraction
    result = [points[0]]
    traversed = 0.0
    for a, b in zip(points, points[1:]):
        segment = distance(a, b)
        if traversed + segment >= target:
            result.append(lerp(a, b, (target - traversed) / segment if segment else 0))
            break
        result.append(b)
        traversed += segment
    return result


def shape_bbox(shape, radius):
    _, x, y, *rest = shape
    if shape[0] == "circle":
        extent = rest[0] + radius
        return x - extent, y - extent, x + extent, y + extent
    width, height, angle = rest
    ex = (abs(width * math.cos(angle)) + abs(height * math.sin(angle))) / 2 + radius
    ey = (abs(width * math.sin(angle)) + abs(height * math.cos(angle))) / 2 + radius
    return x - ex, y - ey, x + ex, y + ey


def overlaps_circle(shape, p, radius):
    kind, x, y, *rest = shape
    dx, dy = p[0] - x, p[1] - y
    if kind == "circle":
        return math.hypot(dx, dy) <= rest[0] + radius
    width, height, angle = rest
    cos, sin = math.cos(angle), math.sin(angle)
    lx, ly = dx * cos + dy * sin, -dx * sin + dy * cos
    qx = max(abs(lx) - abs(width) / 2, 0)
    qy = max(abs(ly) - abs(height) / 2, 0)
    return qx*qx + qy*qy <= radius*radius


class PotionFailed(RuntimeError):
    """A failed brew remains available for inspection/undo in the playground."""


class Forcefield:
    def __init__(self, colliders):
        self.polygons = []
        for collider in colliders:
            offset = (collider["position"]["x"] + collider["offset"]["x"],
                      collider["position"]["y"] + collider["offset"]["y"])
            for path in collider["paths"]:
                self.polygons.append([(p["x"]+offset[0], p["y"]+offset[1]) for p in path])

    def closest_point(self, point):
        closest, best = point, math.inf
        for polygon in self.polygons:
            inside = False
            for a, b in zip(polygon, polygon[1:] + polygon[:1]):
                if (a[1] > point[1]) != (b[1] > point[1]):
                    crossing = a[0] + (point[1]-a[1])*(b[0]-a[0])/(b[1]-a[1])
                    if point[0] < crossing:
                        inside = not inside
            if inside:
                return point
            for a, b in zip(polygon, polygon[1:] + polygon[:1]):
                dx, dy = b[0]-a[0], b[1]-a[1]
                denominator = dx*dx+dy*dy
                t = min(1, max(0, ((point[0]-a[0])*dx+(point[1]-a[1])*dy)/denominator)) if denominator else 0
                candidate = lerp(a, b, t)
                d = distance(point, candidate)
                if d < best:
                    closest, best = candidate, d
            if inside or best < 1e-12:
                return point
        return closest

    def correct(self, point, radius, distance_to_fail=0.0):
        closest = self.closest_point(point)
        d = distance(point, closest)
        correction = d-radius-distance_to_fail
        return (lerp(point, closest, correction/d) if correction > 0 else point), correction


class ZoneIndex:
    def __init__(self, zones, radius, cell_size=3.0):
        self.radius = radius
        self.cell_size = cell_size
        self.shapes = []
        self.cells = defaultdict(list)
        for zone, shapes in zones.items():
            for shape in shapes:
                index = len(self.shapes)
                self.shapes.append((zone, shape))
                xmin, ymin, xmax, ymax = shape_bbox(shape, radius)
                for ix in range(math.floor(xmin / cell_size), math.floor(xmax / cell_size) + 1):
                    for iy in range(math.floor(ymin / cell_size), math.floor(ymax / cell_size) + 1):
                        self.cells[ix, iy].append(index)

    def at(self, position, radius=None):
        radius = self.radius if radius is None else radius
        if not 0 <= radius <= self.radius:
            raise ValueError("Query radius must fit the indexed indicator radius")
        cell = (math.floor(position[0] / self.cell_size),
                math.floor(position[1] / self.cell_size))
        return {zone for i in self.cells.get(cell, ())
                for zone, shape in (self.shapes[i],)
                if overlaps_circle(shape, position, radius)}


class BrewWorld:
    def __init__(self):
        self.ingredients = {d["name"]: d for d in read("ingredients.json") if d["name"] != "Default"}
        self.bases = read("bases.json")
        self.settings = read("brewing_settings.json")
        self.geometry = read("geometry.json")
        self.salts = {d["data"]["m_Name"]: d["data"] for d in read("salts_full.json")}
        self.bellows = read("bellows_controls.json")[0]["data"]
        self.pouring_controls = read("pouring_controls.json")[0]["data"]
        self.unity_settings = read("unity_simulation_settings.json")
        timestep = self.unity_settings["TimeManager"]["data"]["Fixed Timestep"]
        self.fixed_dt = timestep["m_Count"] * timestep["m_Rate"]["m_Denominator"] / timestep["m_Rate"]["m_Numerator"]
        self.collision_matrix = self.unity_settings["Physics2DSettings"]["data"]["m_LayerCollisionMatrix"]
        self.zones = {base: ZoneIndex(read(f"level{number}_zones.json"),
                                      self.geometry["indicator_radius"])
                      for base, number in LEVEL.items()}
        self.vortices = {base: read(f"level{number}_vortices.json")
                         for base, number in LEVEL.items()}
        self.boundaries = {base: read(f"level{number}_boundaries.json")
                           for base, number in LEVEL.items()}
        self.forcefields = {base: Forcefield(colliders) for base, colliders in self.boundaries.items()}
        self.spacing = self.settings["RecipeMapManagerPathSettings"]["ingredientPathSpacingPhysics"]
        self._ingredient_samples = {}

    def ingredient_path(self, name, grind=0.0, graphics=False):
        item = self.ingredients[name]
        spacing = (self.settings["RecipeMapManagerPathSettings"]["ingredientPathSpacingGraphics"]
                   if graphics else self.spacing)
        key = (name, spacing)
        if key not in self._ingredient_samples:
            self._ingredient_samples[key] = sampled_path(item["bezier_path"], spacing)
        points = list(self._ingredient_samples[key])
        fraction = item["grinded_path_starts_from"] + min(1, max(0, grind)) * (1 - item["grinded_path_starts_from"])
        return cut_path(points, fraction)

    def layers_collide(self, first, second):
        return bool(self.collision_matrix[first] & (1 << second))

    def teleport_fade_profile(self, base, position, fade_out=True, samples=200):
        """Contact/damage profile over animation status, before frame scheduling.

        Actual fixed/update ordering must be supplied by the future scheduler;
        this computes only the exact resource curves and sampled contact spans.
        """
        if samples < 1:
            raise ValueError("Samples must be positive")
        teleport = self.settings["RecipeMapManagerTeleportationSettings"]
        curve = teleport["indicatorDisappearingScaleCurve" if fade_out else "indicatorAppearingScaleCurve"]
        profile = []
        total_damage = 0.0
        for index in range(samples):
            progress = (index + .5) / samples
            scale = min(1.0, max(0.0, curve_value(curve, progress)))
            zones = self.zones[base].at(position, self.geometry["indicator_radius"] * scale)
            prefix = "Strong" if "strong_danger" in zones else "Weak" if "weak_danger" in zones else None
            damage = teleport[f"total{prefix}IndicatorDamageOnFade{'Out' if fade_out else 'In'}"] / samples if prefix else 0
            total_damage += damage
            profile.append({"progress": progress, "scale": scale,
                            "zones": sorted(zones), "damage": damage})
        return {"profile": profile, "damage": total_damage,
                "status": "contact profile only; frame scheduling not yet integrated"}

    def effect_scores(self, base, position, rotation=0.0):
        radius = self.geometry["indicator_radius"] + self.geometry["effect_radius"]
        result = []
        for effect in self.bases[base]["effects"]:
            d = distance(position, xy(effect["Position"]))
            angle = abs((rotation - effect["Rotation"] + 180) % 360 - 180)
            settings = self.settings["RecipeMapManagerPotionEffectsSettings"]
            score = min(1.0, max(0.0, curve_value(settings["effectPowerDistanceDependence"], d)
                                 + curve_value(settings["effectPowerAngleDistanceDependence"], angle)))
            tier = (3 if score >= 1 else 2 if score >= settings["middleEffectPowerPosition"] else 1) if d <= radius else 0
            result.append({"name": effect["name"], "distance": d,
                           "angle": angle, "score": score, "tier": tier})
        return sorted(result, key=lambda x: x["distance"])


@dataclass
class PotionSession:
    world: BrewWorld
    base: str = "Water"
    position: tuple[float, float] = (0.0, 0.0)
    rotation: float = 0.0
    health: float = 1.0
    minimum_health: float = 1.0
    pending: list[tuple[float, float]] = field(default_factory=list)
    ingredients_used: Counter = field(default_factory=Counter)
    effects: list[tuple[str, int]] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    salts_used: Counter = field(default_factory=Counter)
    collected: set[str] = field(default_factory=set)
    traveled: list[list[tuple[float, float]]] = field(default_factory=list)
    path_sections: list[dict] = field(default_factory=list)
    teleports: list[dict] = field(default_factory=list)
    failed_reason: str | None = None
    heat: float = 0.0
    start_mode: str = "base"
    rotation_tween: RotationTween | None = None

    @property
    def target_rotation(self):
        return self.rotation_tween.target if self.rotation_tween else self.rotation

    def _advance_rotation(self, seconds):
        if self.rotation_tween is None:
            return
        previous, current = self.rotation_tween.advance(seconds)
        # Match onAngleChanged: the normalized visual angles' difference is
        # passed to fixed hints, including across the 0/360 boundary.
        delta = current - previous
        self.pending = [rotate_about(p, self.position, delta) for p in self.pending]
        self.rotation = current

    def _stop_rotation(self):
        # SetRotatorType cancels the old tween at its current visual value.
        self.rotation_tween = None

    def _fail(self, reason):
        self.failed_reason = reason
        if self.traveled:
            self.traveled[-1].append(self.position)
        raise PotionFailed(reason)

    def _check_bounds(self):
        size = self.world.bases[self.base]["map_size"]
        # KillOutOfMap uses Unity Rect.Contains: lower bound inclusive, upper
        # bound exclusive. Indicator/meta coordinates are centered on the map.
        if not (-size["x"]/2 <= self.position[0] < size["x"]/2
                and -size["y"]/2 <= self.position[1] < size["y"]/2):
            self._fail(f"药瓶越出地图背景矩形：{self.position}")

    def _ensure_sections(self):
        if self.pending and not self.path_sections:
            self.path_sections = [{"name": "legacy", "grind": None,
                                   "teleport": False, "point_count": len(self.pending)}]
        if sum(section["point_count"] for section in self.path_sections) != len(self.pending):
            raise ValueError("Path sections and pending points are inconsistent")

    def _remove_first_point(self):
        self._ensure_sections()
        self.pending.pop(0)
        self.path_sections[0]["point_count"] -= 1
        if self.path_sections[0]["point_count"] == 0:
            self.path_sections.pop(0)

    @property
    def remaining_length(self):
        points = [self.position, *self.pending]
        return sum(distance(a, b) for a, b in zip(points, points[1:]))

    def move_remaining_path(self, position, angle_delta=0.0):
        """External movement carries the unconsumed path; stirring consumes it."""
        dx, dy = position[0] - self.position[0], position[1] - self.position[1]
        self.pending = [rotate_about((p[0] + dx, p[1] + dy), position, angle_delta)
                        for p in self.pending]
        self.position = position
        self.rotation = (self.rotation + angle_delta) % 360
        if angle_delta:
            self._stop_rotation()

    def add(self, name, grind=0.0):
        teleport = bool(self.world.ingredients[name]["is_teleportation"])
        path = self.world.ingredient_path(name, grind, graphics=teleport)
        self._ensure_sections()
        start = self.pending[-1] if self.pending else self.position
        self.pending.extend((start[0]+p[0], start[1]+p[1]) for p in path[1:])
        if len(path) > 1:
            self.path_sections.append({"name": name, "grind": grind,
                                       "teleport": teleport, "point_count": len(path)-1})
        self.ingredients_used[name] += 1
        self.actions.append(f"add({name!r}, grind={grind})")

    def _health_step(self, new_position, zones=None, extra_damage=0.0):
        d = distance(self.position, new_position)
        if zones is None:
            zones = self.world.zones[self.base].at(new_position)
        indicator = self.world.settings["RecipeMapManagerIndicatorSettings"]
        if "strong_danger" in zones:
            self.health += indicator["indicatorStrongHealthDecreasingCoefficient"] * d
        elif "weak_danger" in zones:
            self.health += indicator["indicatorWeakHealthDecreasingCoefficient"] * d
        if "heal" in zones:
            self.health += indicator["indicatorHealingInZoneCoefficient"] * d
        self.health -= extra_damage
        if not zones.intersection({"strong_danger", "weak_danger", "heal"}):
            base = self.world.bases[self.base]
            self.health = 1.0 if base["instant_regeneration"] else self.health + base["regeneration_coefficient"] * d
        self.health = min(1.0, max(0.0, self.health))
        self.minimum_health = min(self.minimum_health, self.health)
        self.position = new_position
        self._check_bounds()
        if self.health <= 0:
            self._fail(f"生命值耗尽：{new_position}")

    def _teleport(self, dt=1/60, stirring=1.0):
        """Complete one crystal, using explicit approximate render-frame timing.

        Collider queries here are immediate. Unity's fixed-step trigger lag and
        component update ordering are NOT reproduced; exported frames expose
        this approximation. Future hints stay at their existing world points.
        """
        self._ensure_sections()
        section = self.path_sections[0]
        count = section["point_count"]
        points = [self.position, *self.pending[:count]]
        self._run_teleport(points, section["name"], dt, stirring, "crystal")
        del self.pending[:count]
        self.path_sections.pop(0)

    def _run_teleport(self, points, name, dt=1/60, stirring=0.0, kind="vortex"):
        start_position = self.position
        settings = self.world.settings["RecipeMapManagerTeleportationSettings"]
        speed = (settings["baseIndicatorSpeed"] * curve_value(settings["baseSpeedMultiplierHeatDependence"], self.heat)
                 + stirring * self.world.settings["RecipeMapManagerIndicatorSettings"]["indicatorSpeed"]
                 * settings["indicatorSpeedMultiplier"])
        record = {"name": name, "kind": kind, "path": points, "frames": [],
                  "dt": dt, "stirring": stirring, "duration": 0.0, "minimum_health": self.health,
                  "model": "immediate contacts; approximate render frames"}
        self.teleports.append(record)
        elapsed = 0.0

        def capture(phase, status, radius, zones):
            record["frames"].append({"phase": phase, "time": elapsed, "status": status,
                                     "radius": radius, "zones": sorted(zones),
                                     "health": self.health, "position": self.position})
            record["duration"] = elapsed
            record["minimum_health"] = min(record["minimum_health"], self.health)

        def fade(fade_out):
            nonlocal elapsed
            phase = "fade_out" if fade_out else "fade_in"
            duration = settings["indicatorDisappearTime" if fade_out else "indicatorAppearTime"]
            curve = settings["indicatorDisappearingScaleCurve" if fade_out else "indicatorAppearingScaleCurve"]
            progress = 0.0
            while progress < 1:
                previous = progress
                progress = min(1.0, progress + speed / settings["baseIndicatorSpeed"] * dt / duration)
                elapsed += dt
                self._advance_rotation(dt)
                self._cool_heat(dt)
                radius = self.world.geometry["indicator_radius"] * min(1.0, max(0.0, curve_value(curve, progress)))
                # EndAnimation disables damage in the completion frame; fade-out
                # also switches the collider to layer 0 (noncolliding with zones).
                zones = set() if fade_out and progress == 1 else self.world.zones[self.base].at(self.position, radius)
                prefix = "Strong" if "strong_danger" in zones else "Weak" if "weak_danger" in zones else None
                damage = (settings[f"total{prefix}IndicatorDamageOnFade{'Out' if fade_out else 'In'}"]
                          * (progress - previous)) if prefix and progress < 1 else 0.0
                try:
                    self._health_step(self.position, zones=zones, extra_damage=damage)
                finally:
                    capture(phase, progress if fade_out else progress-1, radius, zones)

        fade(True)
        # Layer 0 cannot trigger RecipeMapContent (layer 8). Regeneration still
        # runs: instant for water/oil, distance-dependent for wine.
        length = sum(distance(a, b) for a, b in zip(points, points[1:]))
        traversed, index, segment_start = 0.0, 1, 0.0
        while traversed < length - 1e-10:
            traversed = min(length, traversed + speed * dt)
            while index < len(points)-1 and segment_start + distance(points[index-1], points[index]) < traversed:
                segment_start += distance(points[index-1], points[index])
                index += 1
            segment = distance(points[index-1], points[index])
            position = lerp(points[index-1], points[index], (traversed-segment_start)/segment if segment else 1)
            elapsed += dt
            self._advance_rotation(dt)
            self._cool_heat(dt)
            try:
                self._health_step(position, zones=set())
            finally:
                capture("transit", 1, 0, set())
        if kind == "vortex":
            # VortexMapItem restores pathShift at arrival: all unconsumed
            # hints move with the bottle. Crystals keep future hints fixed.
            dx, dy = self.position[0]-start_position[0], self.position[1]-start_position[1]
            self.pending = [(p[0]+dx, p[1]+dy) for p in self.pending]
        fade(False)
        record["duration"] = elapsed
        record["minimum_health"] = min(frame["health"] for frame in record["frames"])
        return elapsed

    def _cool_heat(self, dt, bellows_delta=0.0):
        control = self.world.bellows
        self.heat = min(1.0, max(0.0, self.heat
                       + curve_value(control["heatIncreasingSpeed"], bellows_delta)
                       - (0 if control["disableCoolingDown"] else curve_value(control["heatDecreasingSpeed"], self.heat)*dt)))

    def touching_vortex(self):
        radius = self.world.geometry["indicator_radius"]
        return next((v for v in self.world.vortices[self.base]
                     if distance(self.position, (v["entry"]["x"]+v["entry_offset"]["x"],
                                                 v["entry"]["y"]+v["entry_offset"]["y"]))
                     <= v["entry_radius"]+radius), None)

    def _advance_environment(self, dt, bellows_delta=0.0):
        """Explicit approximate render order: heat -> effect -> vortex.

        Trigger contacts are queried immediately. The original game's component
        scheduling/physics lag and rotation tweens require further calibration.
        """
        self._advance_rotation(dt)
        self._cool_heat(dt, bellows_delta)
        self._health_step(self.position)
        candidate = self.nearest_effect() if self.heat == 1 else None
        if candidate and candidate["tier"]:
            # Invalid effect combinations should not stop time or vortex motion.
            try:
                self.heat_effect()
            except ValueError:
                pass
        if self.heat <= 0:
            return False
        vortex = self.touching_vortex()
        if vortex is None:
            return False
        settings = self.world.settings["RecipeMapManagerVortexSettings"]
        movement = curve_value(settings["vortexMovementFromHeatDependence"], self.heat)*settings["vortexMovementSpeed"]*dt
        center = xy(vortex["entry"])
        d = distance(self.position, center)
        if movement <= 0:
            return False
        if d <= .001 and movement > .001:
            old_position = self.position
            self.move_remaining_path(center)
            self.position = old_position
            self._health_step(center)
            spacing = self.world.settings["RecipeMapManagerPathSettings"]["vortexPathSpacingGraphics"]
            path = sampled_path(vortex["path"], spacing)
            points = [(center[0]+p[0], center[1]+p[1]) for p in path]
            self._run_teleport(points, vortex["name"], dt=dt, kind="vortex")
            return True
        power = settings["vortexSpiralThetaPower"]
        spiral_step = math.copysign(settings["vortexSpiralStep"], power)
        theta = (d*2*math.pi/spiral_step)**(1/power)
        next_theta = max(0.0, theta-movement)
        next_radius = spiral_step/(2*math.pi)*next_theta**power
        angle = math.atan2(self.position[1]-center[1], self.position[0]-center[0]) + next_theta-theta
        target = (center[0]+next_radius*math.cos(angle), center[1]+next_radius*math.sin(angle))
        step_distance = distance(self.position, target)
        position = lerp(self.position, target, min(1, movement/step_distance)) if step_distance else target
        old_position = self.position
        self.move_remaining_path(position)
        self.position = old_position
        self._health_step(position)
        return False

    def pump_bellows(self, angle=60.0, seconds=.5, dt=1/60):
        """A downstroke with constant angular speed; return stroke adds no heat.

        Angle is accumulated downstroke input (several physical strokes may be
        needed). Once teleportation starts, this command waits for its finish.
        """
        if not 0 <= angle <= 10000 or not 0 < seconds <= 120 or not 0 < dt <= 1:
            raise ValueError("Invalid bellows angle, duration or timestep")
        elapsed = 0.0
        trace = [self.position]
        self.traveled.append(trace)
        while elapsed < seconds-1e-10:
            step = min(dt, seconds-elapsed)
            elapsed += step
            teleported = self._advance_environment(step, angle*step/seconds)
            if teleported:
                break
            trace.append(self.position)
        self.actions.append(f"pump_bellows(angle={angle}, seconds={seconds}, dt={dt})")
        return elapsed

    def wait(self, seconds=.5, dt=1/60):
        return self.pump_bellows(0, seconds, dt)

    def stir(self, fraction=1.0):
        if not 0 <= fraction <= 1:
            raise ValueError("stir fraction must be between 0 and 1")
        if not self.pending or fraction == 0:
            return
        target = self.remaining_length * fraction
        self._ensure_sections()
        trace = [self.position]
        self.traveled.append(trace)
        while self.pending and target > 1e-10:
            if self.path_sections[0]["teleport"]:
                self._teleport()
                # Fade-in completion resets lengthToDeleteFromPath. Remaining
                # normal/crystal hints require a new stirring action.
                break
            segment = distance(self.position, self.pending[0])
            if segment < 1e-10:
                self._remove_first_point()
                continue
            consumed = min(target, segment, self.world.spacing)
            intended = lerp(self.position, self.pending[0], consumed / segment)
            if consumed >= segment - 1e-10:
                self._remove_first_point()
            zones = self.world.zones[self.base].at(self.position)
            factor = 1.0
            if "swamp" in zones:
                factor -= self.world.settings["RecipeMapManagerIndicatorSettings"]["indicatorInSwampPathDeletion"]
            actual = lerp(self.position, intended, factor)
            if "swamp" not in zones:
                actual, correction = self.world.forcefields[self.base].correct(
                    actual, self.world.geometry["indicator_radius"],
                    self.world.settings["RecipeMapManagerForcefieldSettings"]["distanceToFailPotion"])
                if correction > self.world.geometry["indicator_radius"]:
                    self.position = actual
                    self._fail(f"超出力场允许距离：{intended}")
            shift = (actual[0] - intended[0], actual[1] - intended[1])
            self.pending = [(p[0] + shift[0], p[1] + shift[1]) for p in self.pending]
            self._health_step(actual)
            trace.append(self.position)
            target -= consumed
            speed = self.world.settings["RecipeMapManagerIndicatorSettings"]["indicatorSpeed"]
            if "swamp" in zones:
                speed *= self.world.settings["RecipeMapManagerIndicatorSettings"]["indicatorInSwampSpeed"]/factor
            if self._advance_environment(consumed/speed):
                break
        self.actions.append(f"stir({fraction})")

    def pour(self, seconds=0.25, strength=1.0, dt=1/60):
        """Port pouring movement/rotation; each call is a separate pour gesture.

        Frame integration and collider timing remain approximate pending game QA.
        """
        if not 0 <= strength <= 1 or not 0 <= seconds <= 120 or dt <= 0:
            raise ValueError("Invalid pouring duration, strength or timestep")
        if strength == 0 or seconds == 0:
            return
        self._stop_rotation()
        pouring = self.world.settings["RecipeMapManagerPouringSettings"]
        indicator = self.world.settings["RecipeMapManagerIndicatorSettings"]
        elapsed = 0.0
        progress = 0.0
        start_angle = self.rotation
        angle_to_base = (0 - start_angle + 180) % 360 - 180
        if angle_to_base == -180:
            angle_to_base = 180
        trace = [self.position]
        self.traveled.append(trace)
        while elapsed < seconds - 1e-10:
            step = min(dt, seconds - elapsed)
            elapsed += step
            speed = curve_value(pouring["standardSpeedByPouring"], strength)
            if strength > 1 - pouring["thresholdForResettingSpeed"]:
                growing = elapsed - pouring["timeBeforePouringSpeedWillStartGrow"]
                if growing >= 0:
                    speed = min(speed + growing * pouring["speedIncreasingRate"],
                                pouring["maxSpeedByPouring"])
            if "swamp" in self.world.zones[self.base].at(self.position):
                speed *= indicator["indicatorInSwampSpeed"]
            movement = speed * step
            d = distance(self.position, (0, 0))
            fraction = min(1, movement / d) if d else 1
            progress += (1 - progress) * fraction
            rotation_remaining = (0 - self.rotation + 180) % 360 - 180
            if rotation_remaining == -180:
                rotation_remaining = 180
            desired_angle = (start_angle + angle_to_base * progress - self.rotation + 180) % 360 - 180
            max_angle = indicator["ladleIndicatorRotationMaxAngleAbs"] * movement / curve_value(pouring["standardSpeedByPouring"], 1)
            delta = math.copysign(min(abs(desired_angle), max_angle, abs(rotation_remaining)), desired_angle)
            position = lerp(self.position, (0, 0), fraction)
            old_position = self.position
            self.move_remaining_path(position, delta)
            self.position = old_position
            self._health_step(position)
            if not d and not self.world.zones[self.base].at(position).intersection({"strong_danger", "weak_danger", "heal"}):
                base = self.world.bases[self.base]
                if not base["instant_regeneration"]:
                    self.health = min(1, self.health + base["regeneration_coefficient"] * movement)
            trace.append(self.position)
            self.heat = max(0, self.heat-curve_value(self.world.pouring_controls["heatCoolingDependence"], strength)*step)
            if self._advance_environment(step):
                break
        self.actions.append(f"pour(seconds={seconds}, strength={strength})")

    def pour_to_center(self):
        for _ in range(120):
            if distance(self.position, (0, 0)) < 1e-8 and abs((self.rotation + 180) % 360 - 180) < 1e-8:
                break
            self.pour(1)
        else:
            raise RuntimeError("Unable to reach base center")

    def nearest_effect(self):
        return next((e for e in self.world.effect_scores(self.base, self.position, self.target_rotation)
                     if e["name"] not in self.collected), None)

    def rotate_salt(self, salt, amount=1, deferred=False):
        """Legacy completed rotation, or an explicit simultaneous grain batch.

        deferred=True keeps the source's target/visual split; time advances via
        subsequent operations. Grain arrival timing and Unity update ordering
        remain caller-specified/approximate, rather than inferred from a batch.
        """
        if deferred:
            if isinstance(amount, bool) or not math.isfinite(amount) or amount != int(amount):
                raise ValueError("Deferred rotation requires whole salt grains")
            controller = self.rotation_tween or RotationTween(target=self.rotation, visual=self.rotation)
            controller.salt_batch(self.world.settings["RecipeMapManagerIndicatorSettings"], salt, int(amount))
            self.rotation_tween = controller
            self.salts_used[salt] += amount
            self.actions.append(f"rotate_salt({salt!r}, {amount}, deferred=True)")
            return
        if salt not in ("sun", "moon") or amount < 0:
            raise ValueError("salt must be 'sun' or 'moon'; amount >= 0")
        self._stop_rotation()
        key = "sunSaltIndicatorRotationAngle" if salt == "sun" else "moonSaltIndicatorRotationAngle"
        # IndicatorRotationSubManager.RotateBy subtracts the salt parameter.
        delta = -amount * self.world.settings["RecipeMapManagerIndicatorSettings"][key]
        self.move_remaining_path(self.position, delta)
        self.salts_used[salt] += amount
        self.actions.append(f"rotate_salt({salt!r}, {amount})")

    def life_salt(self, amount=1):
        if amount < 0:
            raise ValueError("Salt amount must be nonnegative")
        self.health = min(1, self.health + amount * self.world.salts["Life Salt"]["healthToAdd"])
        self.salts_used["life"] += amount
        self.actions.append(f"life_salt({amount})")

    def philosophers_salt(self, amount=1, dt=1/60):
        """Dissolve a simultaneous batch and wait until its lifetimes expire.

        One OnCauldronDissolve adds one independent life=1 packet. This action
        does not reproduce individual grain arrival times or overlapping input.
        Rotation tweens/physics callbacks are approximate, as for pouring.
        """
        if amount < 0 or amount != int(amount) or not 0 < dt <= 1:
            raise ValueError("Philosopher's Salt requires a nonnegative integer amount and dt in (0, 1]")
        if not amount:
            return
        self.salts_used["philosopher"] += amount
        settings = self.world.settings["RecipeMapManagerIndicatorSettings"]
        remaining_life, progress = 1.0, 0.0
        start_angle = self.rotation
        trace = [self.position]
        self.traveled.append(trace)
        angle_on_start = None
        while remaining_life > .0001:
            candidates = [effect for effect in self.world.bases[self.base]["effects"]
                          if effect["name"] not in self.collected]
            if not candidates:
                break
            effect = min(candidates, key=lambda e: distance(self.position, xy(e["Position"])))
            destination = xy(effect["Position"])
            target_angle = effect["Rotation"] % 360
            portion = min(remaining_life, dt/settings["philosophersSaltLifeTime"]
                          if settings["philosophersSaltLifeTime"] else 1)
            remaining_life -= portion
            factor = settings["indicatorInSwampSpeed"] if "swamp" in self.world.zones[self.base].at(self.position) else 1
            movement = amount * portion * settings["philosophersSaltMovesBy"] * factor
            max_angle = amount * portion * settings["philosophersSaltIndicatorRotationMaxAngleAbs"] * factor
            d = distance(self.position, destination)
            fraction = min(1, movement/d) if d else 1
            angle_remaining = (target_angle-self.rotation+180) % 360 - 180
            if angle_remaining == -180:
                angle_remaining = 180
            if angle_on_start is None:
                angle_on_start = angle_remaining
            progress += (1-progress)*fraction
            desired_angle = (start_angle + angle_on_start*progress-self.rotation+180) % 360 - 180
            delta = math.copysign(min(abs(desired_angle), max_angle, abs(angle_remaining)), desired_angle)
            position = lerp(self.position, destination, fraction)
            old_position = self.position
            self.move_remaining_path(position, delta)
            self.position = old_position
            self._health_step(position)
            trace.append(self.position)
            if self._advance_environment(dt):
                break
            if self.position == destination and self.rotation == target_angle:
                break
        self.actions.append(f"philosophers_salt({amount}, dt={dt})")

    def void_salt(self, amount=1):
        if amount < 0:
            raise ValueError("Salt amount must be nonnegative")
        total = self.remaining_length
        self._ensure_sections()
        retained = max(0, total - amount * self.world.salts["Void Salt"]["lengthToErase"])
        self.pending = cut_path([self.position, *self.pending], retained / total)[1:] if retained else []
        count = len(self.pending)
        remaining_sections = []
        for section in self.path_sections:
            taken = min(count, section["point_count"])
            if taken:
                remaining_sections.append({**section, "point_count": taken})
            count -= taken
        self.path_sections = remaining_sections
        self.salts_used["void"] += amount
        self.actions.append(f"void_salt({amount})")

    def heat_effect(self, name=None):
        candidate = self.nearest_effect()
        if candidate is None or candidate["tier"] == 0 or (name is not None and candidate["name"] != name):
            raise ValueError("No requested effect is touching the potion")
        if candidate["name"] in self.collected:
            raise ValueError("This map effect has already been collected")
        slots = [effect for effect, tier in self.effects for _ in range(tier)]
        existing = slots.count(candidate["name"])
        if existing + candidate["tier"] > 3 or (existing and slots[-1] != candidate["name"]):
            raise ValueError("Effect order or tier limit prevents collection")
        slots = (slots + [candidate["name"]] * candidate["tier"])[-5:]
        self.effects = []
        for effect in slots:
            if self.effects and self.effects[-1][0] == effect:
                self.effects[-1] = (effect, self.effects[-1][1] + 1)
            else:
                self.effects.append((effect, 1))
        self.collected.add(candidate["name"])
        self.heat = self.world.bellows["heatOnEffectApply"]
        self.actions.append(f"heat_effect({candidate['name']!r})")
        return self.effects[-1]


if __name__ == "__main__":
    world = BrewWorld()
    potion = PotionSession(world)
    potion.add("Firebell")
    potion.stir()
    print({"position": potion.position, "health": potion.health,
           "nearest": potion.nearest_effect(), "used": potion.ingredients_used})
