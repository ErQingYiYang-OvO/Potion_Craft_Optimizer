"""User-defined resource objective, independent from recipe feasibility."""
import math
from fractions import Fraction

SALT_UNITS_PER_INGREDIENT = {'void':200, 'sun':100, 'moon':100, 'life':50}


def competitive_tiers(cost, incumbents):
    """Grades whose fixed paid inventory is not dominated in both objectives.

    Equality is retained for possible operation-tolerance improvements. An
    absent bound keeps that grade. This does not prune recipes that can drop
    paid ingredients: callers must use it only for a fixed inventory.
    """
    wanted=set()
    for tier in (1,2,3):
        for objective in ('P1','P2'):
            secondary='P2' if objective=='P1' else 'P1'
            incumbent=incumbents.get((objective,tier))
            rank=lambda c:(Fraction(c[f'{objective}_exact']),Fraction(c[f'{secondary}_exact']))
            if incumbent is None or rank(cost)<=rank(incumbent):wanted.add(tier);break
    return wanted


def no_salt_search_bound(records,effect,objective):
    """One search seeks all grades: a cheap tier I must not exclude tier III."""
    per_tier=[]
    for tier in (1,2,3):
        options=[record for record in records if record['effect']==effect and record['tier']==tier
                 and not any(record.get('salts',{}).values())]
        if not options:return None
        field='ingredient_count' if objective=='P1' else 'ingredient_value'
        per_tier.append(min(record[field] for record in options))
    return max(per_tier)


def resource_cost(ingredients, salts, prices):
    """Return exact proportional resource accounting (no rounding-up)."""
    herb_count = 0
    herb_value = Fraction(0)
    for name, count in ingredients.items():
        if name not in prices or not isinstance(count, int) or count < 0:
            raise ValueError('Unknown ingredient or invalid whole-item count')
        herb_count += count
        herb_value += Fraction(str(prices[name])) * count
    salt_equivalent = Fraction(0)
    detail = {}
    for name, amount in salts.items():
        if name not in SALT_UNITS_PER_INGREDIENT:
            raise ValueError('Only void, sun, moon and life salts are allowed; philosopher is forbidden')
        if not math.isfinite(amount) or amount < 0:
            raise ValueError('Salt use must be finite and nonnegative')
        equivalent = Fraction(str(amount)) / SALT_UNITS_PER_INGREDIENT[name]
        value = equivalent * Fraction(str(prices['Watercap']))
        salt_equivalent += equivalent
        detail[name] = {'amount':amount, 'equivalent':float(equivalent), 'value':float(value)}
    p1 = herb_count + salt_equivalent
    p2 = herb_value + salt_equivalent * Fraction(str(prices['Watercap']))
    return {'ingredient_count':herb_count, 'ingredient_value':float(herb_value),
            'salt_equivalent':float(salt_equivalent), 'salt_detail':detail,
            'P1':float(p1), 'P2':float(p2),
            'P1_exact':str(p1), 'P2_exact':str(p2)}
