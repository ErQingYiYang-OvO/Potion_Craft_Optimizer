"""Readable six-objective result index, with honest coverage and replay files."""
from __future__ import annotations
import csv
import hashlib
import html
import json
import argparse
import time
from pathlib import Path

from engine.brew import BrewWorld, PotionSession, xy, distance
from optimizer.costs import resource_cost
from optimizer.verify import verify_record
from optimizer.robustness import recipe_key, current_result

ROOT=Path(__file__).resolve().parent.parent
RESULT=ROOT/'result'
BASE_ZH={'Water':'水','Oil':'油','Wine':'葡萄酒'}
SALT_ZH={'sun':'日之盐','moon':'月之盐','life':'生命之盐','void':'虚无之盐'}
VERIFICATION_CACHE={}


def robustness_text(result):
    if not isinstance(result,dict):return '容错采样：待评估。'
    return (f'容错采样：{result["passed"]}/{result["samples"]} 次通过；'
            '研磨/部分搅拌 ±0.1 个百分点，倒液/等待 ±0.005 秒，盐 ±1 单位。'
            '仅为采样，不是容错证明。')


def fingerprint():
    paths=sorted((ROOT/'data').glob('*.json'))+sorted((ROOT/'engine').glob('*.py'))+[ROOT/'playground/serve.py',ROOT/'docs/PLAN.md']+sorted((ROOT/'optimizer').glob('*.py'))
    hashes={str(path.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    return {'sha256':hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest(),'files':hashes}


def write_atomic(path,content):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(content,encoding='utf-8')
    temporary.replace(path)


def operation_text(action,ui):
    kind=action['kind']
    if kind=='add':return f"研磨 {action['grind']*100:.6f}% 的{ui['ingredients'][action['name']]['name']}，加入一件"
    if kind=='stir':return f"搅拌当前剩余路径的 {action['fraction']*100:.6f}%"
    if kind=='pour':return f"加入基液 {action['seconds']:.8f} 秒，强度 {action['strength']*100:g}%"
    if kind=='pump':return f"鼓风累计下压 {action['angle']:g}°，持续 {action['seconds']:g} 秒"
    if kind=='salt':return f"加入{SALT_ZH[action['salt']]} {action['amount']:g} 单位"+('，保留旋转动画' if action.get('deferred') else '')
    if kind=='wait':return f"等待 {action['seconds']:g} 秒"
    if kind=='center':return '倒液至中心'
    raise ValueError(kind)


def make_reports():
    world=BrewWorld()
    prices={name:item['price'] for name,item in world.ingredients.items()}
    ui=json.loads((ROOT/'data/ui_manifest.json').read_text(encoding='utf-8'))
    robustness={}
    for robustness_path in sorted((RESULT/'search').glob('robustness*.json')):
        statistics=json.loads(robustness_path.read_text(encoding='utf-8'))
        robustness.update({key:value for key,value in statistics.items() if current_result(value)})
    pool=[]
    runs=[]
    verification_cache=VERIFICATION_CACHE
    rejected=[]
    for source in (RESULT/'search').glob('*candidates.json'):
        document=json.loads(source.read_text(encoding='utf-8'))
        runs+=[{**run,'source':str(source.relative_to(ROOT)).replace('\\','/')} for run in document.get('runs',[])]
        for entry in document.get('records',{}).values():
            if entry.get('replay_verified') and not entry.get('failed_reason'):
                key=json.dumps({k:entry.get(k) for k in ('base','effect','tier','operations','ingredients','salts')},sort_keys=True)
                if key not in verification_cache:
                    try:verification_cache[key]=verify_record(entry,details=True)
                    except (ValueError,KeyError,TypeError) as error:
                        verification_cache[key]={'verification_error':str(error)}
                if 'verification_error' in verification_cache[key]:
                    rejected.append({'effect':entry.get('effect'),'error':verification_cache[key]['verification_error']})
                else:
                    pool.append({**entry,**verification_cache[key]})
    stamp=fingerprint()
    manifest={'gameVersion':'2.0.2','dataFingerprint':stamp,'engineStatus':'calibrating',
              'saltRules':{'forbidden':['philosopher'],'unitsPerEquivalent':{'void':200,'sun':100,'moon':100,'life':50},
                           'referenceIngredient':'Watercap','referencePrice':prices['Watercap']},
              'records':[],'coverage':{},'runs':runs,'rejected_candidates':rejected}
    for objective in ('P1','P2'):
        directory=RESULT/objective
        directory.mkdir(parents=True,exist_ok=True)
        rows=[]
        markdown=[f'# {objective}：配方结果（持续更新）','',
                  '候选通过现有引擎回放；尚未通过实际游戏复核。引擎的帧时序、动作重叠等仍在校准。',
                  '搜索是启发式，除明确写出的简单资源下界证书外，没有全局最优证明。搜索未找到不等于不可行。',
                  '',f'数据与引擎指纹：`{stamp["sha256"]}`','',
                  '含盐模式包含无盐配方作为候选；不允许贤者之盐。盐按用户给定水之盖等价规则计价。',
                  '小数操作是引擎控制量，不代表已能在游戏中按显示精度执行；操作误差范围尚待核对。','']
        for mode in ('no_salt','with_salt'):
            selected=0
            markdown += ['## '+('无盐基准' if mode=='no_salt' else '允许四种盐'),'','| 药效 | 等级 | 基液 | 药材件数 | P1 等价消耗 | P2 基础价值 | 下界 | 状态 |','|---|---:|---|---:|---:|---:|---:|---|']
            for name in sorted(ui['effects'],key=lambda n:ui['effects'][n]['name']):
                for tier in (1,2,3):
                    options=[e for e in pool if e['effect']==name and e['tier']==tier and
                             (mode=='with_salt' or not any(e.get('salts',{}).values()))]
                    def selection_key(entry):
                        tested=robustness.get(recipe_key(entry),{})
                        tolerance=tested.get('passed',0)/tested['samples'] if tested.get('samples') else -1
                        return (entry['costs'][objective],entry['costs']['P2' if objective=='P1' else 'P1'],
                                -tolerance,len(entry['operations']))
                    best=min(options,key=selection_key) if options else None
                    label=f'{ui["effects"][name]["name"]} {"ⅠⅡⅢ"[tier-1]}'
                    # Zero-input free operations cannot reach any listed target:
                    # verify initial contacts, effects, and forbidden movement salt.
                    zero=all(distance(xy(e['Position']),(0,0))>world.geometry['indicator_radius']+world.geometry['effect_radius']
                             and not PotionSession(world,base=b).touching_vortex()
                             for b,d in world.bases.items() for e in d['effects'] if e['name']==name)
                    lower=(1. if objective=='P1' else min(prices.values())) if zero else 0.
                    status='尚未找到候选'
                    proof=None
                    if best:
                        selected+=1
                        status='当前最好可行解'
                        if abs(best['costs'][objective]-lower)<1e-12:
                            status=('药材等价消耗' if objective=='P1' else '基础价值')+'已达资源下界（当前引擎模型）'
                            proof='全部合法基液中心均不接触目标或漩涡；禁用贤者之盐后，零药材的倒液/搅拌/加热/四种盐不能使中心位置离开。因此至少一件药材，且价值至少为最低药材基础价值；候选主目标恰达此下界。次级目标与容错未证明最优，游戏未复核。'
                        replay_path=f'{mode}/{name}-{tier}.json'
                        (directory/mode).mkdir(exist_ok=True)
                        replay={'gameVersion':'2.0.2','engineStatus':'calibrating','base':best['base'],
                                'operations':best['operations'],'target':{'effect':name,'tier':tier},
                                'objective':objective,'mode':mode,'costs':best['costs'],
                                'dataFingerprint':stamp['sha256'],'optimality':status,'gameVerified':False}
                        write_atomic(directory/replay_path,json.dumps(replay,ensure_ascii=False,indent=2))
                        ingredients='，'.join(f'{ui["ingredients"][i]["name"]} × {n}' for i,n in best['ingredients'].items())
                        row={'objective':objective,'mode':mode,'effect':name,'name':ui['effects'][name]['name'],'tier':tier,
                             'base':best['base'],'ingredients':ingredients,'salts':best.get('salts',{}),'costs':best['costs'],
                             'lower_bound':lower,'gap':best['costs'][objective]-lower,'status':status,'proof':proof,
                             'replay':f'{objective}/{replay_path}','operations':best['operations'],
                             'steps':[operation_text(op,ui) for op in best['operations']],
                             'health':best['health'],'minimum_action_endpoint_health':best['minimum_action_endpoint_health'],
                             'minimum_health':best['minimum_health'],
                             'robustness':robustness.get(recipe_key(best),'待评估'),'game_verified':False}
                        tested=robustness.get(recipe_key(best),{})
                        stable_options=[entry for entry in options if recipe_key(entry)!=recipe_key(best)
                                        and robustness.get(recipe_key(entry),{}).get('samples',0)>0
                                        and robustness[recipe_key(entry)]['passed']==robustness[recipe_key(entry)]['samples']]
                        if tested.get('passed',-1)!=tested.get('samples',0) and stable_options:
                            alternate=min(stable_options,key=selection_key)
                            alternate_path=f'{mode}/{name}-{tier}-sampled-alternative.json'
                            alternate_recipe={**replay,'base':alternate['base'],'operations':alternate['operations'],
                                              'costs':alternate['costs'],'optimality':'容错采样通过的备选；非最低成本声明'}
                            write_atomic(directory/alternate_path,json.dumps(alternate_recipe,ensure_ascii=False,indent=2))
                            row['sampled_alternative']={'base':alternate['base'],'costs':alternate['costs'],
                                  'ingredients':'，'.join(f'{ui["ingredients"][i]["name"]} × {n}' for i,n in alternate['ingredients'].items()),
                                  'salts':alternate.get('salts',{}),'operations':alternate['operations'],
                                  'steps':[operation_text(op,ui) for op in alternate['operations']],
                                  'robustness':robustness[recipe_key(alternate)],'replay':f'{objective}/{alternate_path}'}
                        markdown.append(f'| {ui["effects"][name]["name"]} | {tier} | {BASE_ZH[best["base"]]} | {best["costs"]["ingredient_count"]} | {best["costs"]["P1"]:.6f} | {best["costs"]["P2"]:.6f} | {lower:g} | {status} |')
                    else:
                        row={'objective':objective,'mode':mode,'effect':name,'name':ui['effects'][name]['name'],'tier':tier,
                             'status':status,'lower_bound':lower,'gap':None}
                        markdown.append(f'| {ui["effects"][name]["name"]} | {tier} | — | — | — | — | {lower:g} | {status} |')
                    manifest['records'].append(row);rows.append(row)
            manifest['coverage'][f'{objective}:{mode}']={'verified_candidates':selected,'total':123}
            markdown+=['',f'已覆盖 {selected}/123 个目标。','']
        markdown+=['## 逐条配方与操作','']
        for row in rows:
            if 'operations' not in row:continue
            markdown += [f'### {row["name"]} {"ⅠⅡⅢ"[row["tier"]-1]} · {"无盐" if row["mode"]=="no_salt" else "含盐允许"}','',
                         f'基液：{BASE_ZH[row["base"]]}。配料：{row["ingredients"]}。盐：{json.dumps(row["salts"],ensure_ascii=False)}。',
                         f'P1={row["costs"]["P1"]:.8f}；P2={row["costs"]["P2"]:.8f}。状态：{row["status"]}。',
                         f'[下载 GUI 操作回放]({row["replay"].split("/",1)[1]})',
                         robustness_text(row['robustness']),'']
            markdown += [f'{i}. {step}' for i,step in enumerate(row['steps'],1)]+['']
            if 'sampled_alternative' in row:
                alternate=row['sampled_alternative']
                markdown += [f'容错采样通过备选：{BASE_ZH[alternate["base"]]}基液，{alternate["ingredients"]}；P1 {alternate["costs"]["P1"]:g}，P2 {alternate["costs"]["P2"]:g}。',
                             robustness_text(alternate['robustness']),f'[下载备选回放]({alternate["replay"].split("/",1)[1]})','']
                markdown += [f'{i}. {step}' for i,step in enumerate(alternate['steps'],1)]+['']
        (directory/'REPORT.md').write_text('\n'.join(markdown)+'\n',encoding='utf-8')
        write_atomic(directory/'results.json',json.dumps(rows,ensure_ascii=False,indent=2))
        with (directory/'summary.csv').open('w',newline='',encoding='utf-8-sig') as handle:
            writer=csv.writer(handle)
            writer.writerow(['模式','药效','等级','基液','药材','盐','P1等价消耗','P2价值','下界','差距','状态'])
            for row in rows:
                costs=row.get('costs',{})
                writer.writerow([row['mode'],row['name'],row['tier'],BASE_ZH.get(row.get('base'),'—'),row.get('ingredients','—'),
                                 json.dumps(row.get('salts',{}),ensure_ascii=False),costs.get('P1'),costs.get('P2'),row['lower_bound'],row['gap'],row['status']])
        (directory/'README.md').write_text(f'# {objective} 求解进展\n\n[完整可读报告](REPORT.md) · [汇总表](summary.csv) · [结构化结果](results.json)\n\n当前覆盖：'+
            '；'.join(f'{mode} {manifest["coverage"][f"{objective}:{mode}"]["verified_candidates"]}/123' for mode in ('no_salt','with_salt'))+
            '。仍在搜索，未覆盖项不判不可行。\n',encoding='utf-8')
    available=[r for r in manifest['records'] if 'operations' in r]
    tested={recipe_key(r):r['robustness'] for r in available if isinstance(r.get('robustness'),dict)}
    unique={recipe_key(r) for r in available}
    missing=[f'{r["name"]}{"ⅠⅡⅢ"[r["tier"]-1]}' for r in manifest['records']
             if r['objective']=='P1' and r['mode']=='no_salt' and 'operations' not in r]
    manifest['tasks']=[
        {'id':'T1','name':'固定资源与盐计价','status':'已实现'},
        {'id':'T2','name':'配方完整回放','status':f'{len(available)} 条展示结果已通过当前引擎'},
        {'id':'T3','name':'补齐无盐候选','status':f'{manifest["coverage"]["P1:no_salt"]["verified_candidates"]}/123'},
        {'id':'T4','name':'含盐候选与三种基液','status':f'{manifest["coverage"]["P1:with_salt"]["verified_candidates"]}/123；完整动作范围待扩大'},
        {'id':'T5','name':'下界与操作容错','status':f'{sum(bool(r.get("proof")) for r in available if r["mode"]=="no_salt")} 项无盐主目标达到资源下界；{len(tested)}/{len(unique)} 条不同展示配方已采样；冷态普通搅拌区间已接地图支持检查；完整酿药区间排除未实现'},
        {'id':'T6','name':'结果浏览与实验台回放','status':'已实现'}]
    manifest['next']={'missing_no_salt':missing,
                      'work':(['补齐缺失等级'] if missing else ['复核并降低已覆盖配方成本'])+
                             ['比较倾斜图标所在基液的低等级成本','扩大途中倒液、旋转及剩余路径操作','推进严格下界与排除证明']}
    write_atomic(RESULT/'manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    markup=['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Potion Craft 求解结果</title>',
            '<style>body{font:15px system-ui;color:#303e35;background:#f5f0e5;max-width:1100px;margin:auto;padding:24px}h1{font-size:25px}details{background:#fffaf0;border:1px solid #d4c7ac;border-radius:9px;margin:9px 0;padding:12px}summary{cursor:pointer}small{color:#81775f}table{border-collapse:collapse}td,th{padding:8px;text-align:left}li{line-height:1.8}a{color:#41654a}.pending{color:#958771}</style>',
            '<h1>Potion Craft · P1/P2 求解进展</h1><p>候选已通过当前引擎回放，实际游戏未复核；搜索与校准仍在进行。盐使用用户指定水之盖等价计价，禁用贤者之盐。</p>',
            '<p><a href="search/snapshots/README.md">搜索运行快照与重跑说明</a></p>',
            '<p><a href="search/elementary_geometry_certificate.json">基础几何区间排除示例（尚不排除酿药配方）</a></p>',
            '<p><a href="search/cold_stir_certificate.json">冷态普通搅拌区间示例（仅固定起始状态和搅拌量范围）</a></p>',
            '<p><a href="P1/REPORT.md">P1 报告</a> · <a href="P2/REPORT.md">P2 报告</a> · <a href="A1/README.md">A1</a> · <a href="A2/README.md">A2</a> · <a href="G1/README.md">G1</a> · <a href="G2/README.md">G2</a></p>',
            '<label>筛选：<select id="objective"><option>P1</option><option>P2</option></select> <select id="mode"><option value="no_salt">无盐</option><option value="with_salt">允许四种盐</option></select> <input id="filter" placeholder="搜索药效名称"></label><p id="coverage"></p>']
    markup.append('<section><h2>工作目标</h2><ul>'+''.join(f'<li>{task["id"]} {html.escape(task["name"])}：{html.escape(task["status"])}</li>' for task in manifest['tasks'])+'</ul>')
    markup.append('<p>无盐待补：'+html.escape('、'.join(missing) if missing else '候选已覆盖全部等级；成本优化与证明继续推进')+'。</p>')
    markup.append('<p>接下来：'+html.escape(' → '.join(manifest['next']['work']))+'。</p></section>')
    for row in manifest['records']:
        searchable=html.escape(row['name'],quote=True)
        markup.append(f'<details data-objective="{row["objective"]}" data-mode="{row["mode"]}" data-name="{searchable}"><summary>{searchable} {"ⅠⅡⅢ"[row["tier"]-1]} · {html.escape(row["status"])}</summary>')
        if 'operations' in row:
            markup.append(f'<p>{BASE_ZH[row["base"]]}基液 · {html.escape(row["ingredients"])}<br>P1 {row["costs"]["P1"]:.6f} · P2 {row["costs"]["P2"]:.6f} · 下界 {row["lower_bound"]:g} · 差距 {row["gap"]:.6f}</p>')
            markup.append('<ol>'+''.join('<li>'+html.escape(step)+'</li>' for step in row['steps'])+'</ol>')
            markup.append(f'<button data-replay="{row["replay"]}">载入实验台</button> · <a href="{row["replay"]}" download>下载 GUI 回放</a><p><small>{html.escape(robustness_text(row["robustness"]))}<br>全程最低生命值 {row["minimum_health"]*100:.2f}%；药材等价消耗达到下界时，也未证明次级价格最优。</small></p>')
            if 'sampled_alternative' in row:
                alternate=row['sampled_alternative']
                markup.append(f'<details><summary>容错采样通过备选 · P1 {alternate["costs"]["P1"]:g} · P2 {alternate["costs"]["P2"]:g}</summary><p>{BASE_ZH[alternate["base"]]}基液 · {html.escape(alternate["ingredients"])}<br>{html.escape(robustness_text(alternate["robustness"]))}</p>')
                markup.append('<ol>'+''.join('<li>'+html.escape(step)+'</li>' for step in alternate['steps'])+'</ol>')
                markup.append(f'<button data-replay="{alternate["replay"]}">载入备选配方</button> · <a href="{alternate["replay"]}" download>下载备选回放</a></details>')
        else:markup.append('<p class="pending">尚未找到经过引擎验证的候选；不代表目标不可行。</p>')
        markup.append('</details>')
    markup.append('<script>const $=id=>document.getElementById(id);function update(){let all=0,found=0;for(const el of document.querySelectorAll("details[data-objective]")){const match=el.dataset.objective===$("objective").value&&el.dataset.mode===$("mode").value;el.hidden=!match||!el.dataset.name.includes($("filter").value.trim());if(match){all++;if(el.querySelector("ol"))found++}}$("coverage").textContent=`已验证候选 ${found}/${all} 个目标`; }for(const id of ["objective","mode","filter"])$(id).addEventListener("input",update);for(const button of document.querySelectorAll("button[data-replay]"))button.onclick=async()=>{button.disabled=true;try{const response=await fetch(button.dataset.replay);if(!response.ok)throw Error("操作文件读取失败");sessionStorage.setItem("potionRecipeReplay",JSON.stringify(await response.json()));location.href="/";}catch(error){button.textContent=error.message;button.disabled=false}};update();</script></html>')
    write_atomic(RESULT/'index.html','\n'.join(markup))
    print(manifest['coverage'])
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--watch',type=int,default=0,help='Seconds to refresh reports when candidate sources change')
    args=parser.parse_args()
    deadline=time.monotonic()+args.watch
    previous=None
    while True:
        sources=sorted((RESULT/'search').glob('*candidates.json'))
        sources+=sorted((RESULT/'search').glob('robustness*.json'))
        digest=tuple((str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in sources)
        if digest!=previous:
            try:make_reports();previous=digest
            except json.JSONDecodeError:pass  # old in-flight writer may be non-atomic
        if not args.watch or time.monotonic()>=deadline:break
        time.sleep(20)
