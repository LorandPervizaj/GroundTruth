"""Select bounded, contact-redacted original corpus regressions."""
from common import *
import re
from groundtruth.gazetteers.loader import GazetteerService
def redact(text):
 text=re.sub(r'https?://\S+|\S+@\S+|(?:www\.|bit\.ly/|t\.co/)\S+','[redacted]',str(text or ''))
 text=re.sub(r'(?<!\d)\+?\d[\d ()/.-]{6,}\d','[contact redacted]',text)
 return text[:1200]
selected={}
city={r['raw_listing_id']:r for r in read(ORIGINAL/'research/prishtina_location_demo/phase4/snapshots/raw_city_metadata.json')}
for row in rows(P/'snapshots/normalized_inputs.jsonl.gz'):
 p=row['parsed'] or {};n=row['normalized'];extra=p.get('extra_fields') or {};title=extra.get('title_en') or extra.get('title') or '';description=p.get('description_original') or '';fold=GazetteerService._normalize(title+' '+description)
 if 'school' not in selected and n.get('district_id')==49 and 'dardani' in fold and 'shkoll' not in fold:
  selected['school']={'case':'original_broad_dardania','title':redact(title),'description':redact(description),'neighborhood_raw':'Dardania','expect_not_district':'shkolla-dardania','source_record_sha256':hashlib.sha256(str(row['record_id']).encode()).hexdigest()}
 if 'letter' not in selected and 'ahmet krasniqi' in fold and 'rruga a' not in fold:
  selected['letter']={'case':'original_ahmet_krasniqi','title':redact(title),'description':redact(description),'street_raw':p.get('street_raw'),'expect_not_district':'rruga-a','source_record_sha256':hashlib.sha256(str(row['record_id']).encode()).hexdigest()}
 raw=city.get(row['raw_listing_id'],{}).get('property_city')
 raw=raw.get('name') if isinstance(raw,dict) else raw
 if 'city' not in selected and n['source_website']=='pro-rks' and raw and 'fushe kosov' in GazetteerService._normalize(raw):
  selected['city']={'case':'original_pro_rks_city','source_city':raw,'source_raw_hash':row['raw_content_hash'],'policy':'Preserve source city, retain legacy pricing compatibility pending review.'}
 if len(selected)==3:break
assert len(selected)==3
dest=ROOT/'tests/fixtures/phase5/location_examples.json';dest.parent.mkdir(parents=True,exist_ok=True);write(dest,list(selected.values()))
write(B/'validation/real_fixture_provenance.json',{'source':'Phase3 frozen originals plus Phase4 hash-matched raw-city supplement','frozen_capture_sha256':digest(P/'snapshots/normalized_inputs.jsonl.gz'),'selected_case_types':list(selected),'redaction':'No contacts/URLs/source listing IDs; bounded original text, record keys hashed.','fixture_sha256':digest(dest)})
print('Selected',list(selected))
