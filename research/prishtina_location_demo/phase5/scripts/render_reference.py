"""Preserve original YAML comments/layout while updating changed semantic fields."""
import json,re,yaml

def render_yaml(desired, baseline_path):
    original=baseline_path.read_text(encoding='utf8')
    original=re.sub(r'^version:.*$', 'version: '+desired['version'],original,flags=re.M)
    original=re.sub(r'^updated:.*$', 'updated: '+json.dumps(str(desired['updated'])),original,flags=re.M)
    original=original.replace('# DRAFT — Prishtina location tree (user-defined v0.3)', '# Phase5 market semantics; legacy scalar tree compatibility retained')
    original=original.replace('- text: "Royal Mall"','- text: "Banesë në kompleksin Royal Mall"')
    targets={n['slug']:n for n in desired['city']['neighborhoods']}
    blocks=list(re.finditer(r'^    - name:.*?(?=^    - name:|^  neighborhoods_tbd:|\Z)',original,re.M|re.S))
    replacements=[];seen=set()
    for match in blocks:
        block=match[0];slug_match=re.search(r'^      slug: ([\w-]+)',block,re.M)
        if not slug_match:continue
        slug=slug_match[1]
        if slug not in targets:continue
        seen.add(slug);target=targets[slug]
        if target.get('aliases'):
            line='      aliases: '+json.dumps(target['aliases'],ensure_ascii=False)
            if re.search(r'^      aliases:',block,re.M):block=re.sub(r'^      aliases:.*$',lambda m:line,block,flags=re.M)
            else:block=re.sub(r'(^      slug:.*$)',lambda m:m[1]+'\n'+line,block,count=1,flags=re.M)
        items={item['slug']:item for item in [*target.get('districts',[]),*target.get('complexes_direct',[]),*[cx for d in target.get('districts',[]) for cx in d.get('complexes',[])]]}
        def flow_update(m):
            line=m[0];s=re.search(r'\bslug: ([\w-]+)',line)
            if not s or s[1] not in items:return line
            raw=yaml.safe_load(line.strip()[2:]);item=items[s[1]]
            if raw==item:return line
            rendered=yaml.safe_dump(item,allow_unicode=True,default_flow_style=True,sort_keys=False,width=10000).strip()
            return line[:len(line)-len(line.lstrip())]+'- '+rendered
        block=re.sub(r'^\s+- \{[^\n]+\}[^\n]*$',flow_update,block,flags=re.M)
        for d in target.get('districts',[]):
            if d['slug'] not in {'rruga-a','rruga-b','rruga-c'}:continue
            aliases='          aliases: '+json.dumps(d.get('aliases',[]),ensure_ascii=False)
            block=re.sub(r'(^          slug: '+re.escape(d['slug'])+r'$)',lambda m:m[1]+'\n'+aliases,block,count=1,flags=re.M)
        replacements.append((match.start(),match.end(),block))
    for start,end,block in reversed(replacements):original=original[:start]+block+original[end:]
    missing=[n for n in desired['city']['neighborhoods'] if n['slug'] not in seen]
    if missing:
        added=yaml.safe_dump(missing,allow_unicode=True,sort_keys=False,width=10000)
        added='\n'.join('    '+line if line else '' for line in added.splitlines())+'\n\n'
        original=original.replace('  neighborhoods_tbd:',added+'  neighborhoods_tbd:')
    keep={n['slug'] for n in desired['city'].get('neighborhoods_tbd',[])}
    section=original.index('  neighborhoods_tbd:')
    head,tail=original[:section],original[section:]
    tail=re.sub(r'^    - \{[^\n]+\}\n',lambda m:m[0] if (s:=re.search(r'slug: ([\w-]+)',m[0])) and s[1] in keep else '',tail,flags=re.M)
    result=head+tail
    assert yaml.safe_load(result)==desired, 'Comment-preserving YAML differs from intended semantics'
    return result
