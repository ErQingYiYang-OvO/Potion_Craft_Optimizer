"""Audit all delivered targets and saved GUI recipes from a stable report."""
import json
import hashlib
from datetime import datetime, timezone
from collections import Counter

from optimizer.verify import verify_record, ROOT
from optimizer.robustness import recipe_key, current_result


def main():
    manifest_path = ROOT/'result/manifest.json'
    manifest_bytes = manifest_path.read_bytes()
    manifest=json.loads(manifest_bytes)
    ui=json.loads((ROOT/'data/ui_manifest.json').read_text(encoding='utf-8'))
    expected={(effect,tier) for effect in ui['effects'] for tier in (1,2,3)}
    failures=[];cache={};counts={};alternate_count=0
    for objective in ('P1','P2'):
        for mode in ('no_salt','with_salt'):
            rows=[r for r in manifest['records'] if r['objective']==objective and r['mode']==mode]
            identities=[(r['effect'],r['tier']) for r in rows]
            if len(set(identities))!=len(identities) or set(identities)!=expected:
                failures.append({'group':f'{objective}:{mode}','error':'Missing or duplicate target rows'})
            counts[f'{objective}:{mode}']=sum('operations' in r for r in rows)
            for row in rows:
                if 'operations' not in row:
                    failures.append({'group':f'{objective}:{mode}','effect':row['effect'],'tier':row['tier'],'error':'No candidate'})
                    continue
                try:
                    path=(ROOT/'result'/row['replay']).resolve()
                    if not path.is_relative_to(ROOT/'result'):raise ValueError('Replay path outside result folder')
                    document=json.loads(path.read_text(encoding='utf-8'))
                    if document['gameVersion']!='2.0.2' or document['base']!=row['base'] or document['operations']!=row['operations']:
                        raise ValueError('Replay file differs from delivered row')
                    if document['target']!={'effect':row['effect'],'tier':row['tier']} or document['mode']!=mode or document['objective']!=objective:
                        raise ValueError('Replay target or mode differs')
                    if document['dataFingerprint']!=manifest['dataFingerprint']['sha256']:raise ValueError('Mixed report fingerprints')
                    ingredients=dict(Counter(a['name'] for a in row['operations'] if a['kind']=='add'))
                    salts=Counter()
                    for action in row['operations']:
                        if action['kind']=='salt':salts[action['salt']]+=action['amount']
                    if mode=='no_salt' and any(salts.values()):raise ValueError('Salt found in no-salt recipe')
                    record={**row,'ingredients':ingredients,'salts':dict(salts)}
                    identity=recipe_key(record)
                    if identity not in cache:cache[identity]=verify_record(record,details=True)
                    verified=cache[identity]
                    for field in ('P1_exact','P2_exact','ingredient_count','salt_equivalent'):
                        if verified['costs'][field]!=row['costs'][field] or document['costs'][field]!=row['costs'][field]:
                            raise ValueError(f'Incorrect delivered cost: {field}')
                    if dict(salts)!=row['salts']:raise ValueError('Incorrect delivered salt inventory')
                    if abs(verified['minimum_health']-row['minimum_health'])>1e-10:raise ValueError('Incorrect minimum health')
                    alternate=row.get('sampled_alternative')
                    if alternate:
                        alternate_count+=1
                        evidence=alternate['robustness']
                        if not current_result(evidence) or evidence['samples']<=0 or evidence['passed']!=evidence['samples']:
                            raise ValueError('Alternate lacks current successful sample evidence')
                        if len(evidence['outcomes'])!=evidence['samples'] or not all(o['passed'] for o in evidence['outcomes']):
                            raise ValueError('Alternate sample outcomes disagree with claimed pass count')
                        alternate_path=(ROOT/'result'/alternate['replay']).resolve()
                        if not alternate_path.is_relative_to(ROOT/'result'):raise ValueError('Alternate path outside result folder')
                        saved=json.loads(alternate_path.read_text(encoding='utf-8'))
                        if saved['base']!=alternate['base'] or saved['operations']!=alternate['operations'] or saved['target']!=document['target']:
                            raise ValueError('Alternate file differs from report')
                        if saved['mode']!=mode or saved['objective']!=objective or saved['dataFingerprint']!=document['dataFingerprint']:
                            raise ValueError('Alternate metadata differs from report')
                        inventory=dict(Counter(a['name'] for a in alternate['operations'] if a['kind']=='add'))
                        alternate_record={**alternate,'effect':row['effect'],'tier':row['tier'],'ingredients':inventory}
                        alternate_identity=recipe_key(alternate_record)
                        if alternate_identity not in cache:cache[alternate_identity]=verify_record(alternate_record,details=True)
                        alternate_costs=cache[alternate_identity]['costs']
                        if mode=='no_salt' and any(alternate['salts'].values()):raise ValueError('Salt in no-salt alternate')
                        for field in ('P1_exact','P2_exact','ingredient_count','salt_equivalent'):
                            if alternate_costs[field]!=alternate['costs'][field] or saved['costs'][field]!=alternate_costs[field]:
                                raise ValueError('Incorrect alternate cost')
                except (ValueError,KeyError,TypeError,OSError) as error:
                    failures.append({'group':f'{objective}:{mode}','effect':row['effect'],'tier':row['tier'],'error':str(error)})
    if manifest_path.read_bytes() != manifest_bytes:
        failures.append({'error':'Manifest changed during audit; rerun against a stable report'})
    snapshot_path = ROOT/'result/search/delivery_snapshot.json'
    snapshot_temp = snapshot_path.with_suffix('.tmp')
    snapshot_temp.write_bytes(manifest_bytes); snapshot_temp.replace(snapshot_path)
    report={'gameVersion':'2.0.2','dataFingerprint':manifest['dataFingerprint']['sha256'],
            'auditedAt':datetime.now(timezone.utc).isoformat(),
            'snapshot':'delivery_snapshot.json','snapshotSha256':hashlib.sha256(manifest_bytes).hexdigest(),
            'targetCounts':counts,'deliveredRows':len(manifest['records']),'uniqueReplayedRecipes':len(cache),
            'sampledAlternativeRows':alternate_count,
            'candidateCoverageComplete':all(n==123 for n in counts.values()) and not failures,
            'failures':failures,'actualGameVerified':False,'objectiveComplete':False,
            'remaining':['Complete legal control/action coverage','Global optimality certificates beyond simple resource bounds',
                         'Resolve engine calibration gaps under the prohibition on launching the game']}
    path=ROOT/'result/search/delivery_audit.json'
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(path)
    print(json.dumps(report,ensure_ascii=False),flush=True)
    if failures:raise SystemExit(1)


if __name__=='__main__':main()
