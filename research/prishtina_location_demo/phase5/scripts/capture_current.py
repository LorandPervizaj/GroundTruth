"""Read-only current snapshot, separate from deterministic October23 baseline."""
from common import *
if (B/'baseline/current_normalized_inputs.jsonl.gz').exists():
 raise SystemExit('Current comparison snapshot already frozen; reuse it rather than overwrite the evidence.')
with connect() as c:
 c.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
 meta=c.execute("SELECT current_setting('transaction_read_only'),pg_current_snapshot()::text,now()::text").fetchone()
 assert meta[0]=='on'
 count,max_id=c.execute('SELECT count(*),max(id) FROM normalized_listings').fetchone()
 fingerprint=c.execute("SELECT md5(string_agg(md5(to_jsonb(n)::text),'' ORDER BY id)) FROM normalized_listings n").fetchone()[0]
 out=B/'baseline/current_normalized_inputs.jsonl.gz'
 sql="""SELECT n.id AS record_id,to_jsonb(n)-'image_urls'-'description_cleaned' AS normalized,to_jsonb(p)-'image_urls'-'description_cleaned' AS parsed,r.id AS raw_listing_id,r.content_hash AS raw_content_hash,r.scraped_at AS raw_scraped_at,jsonb_build_object('title',r.raw_payload->>'title','address',r.raw_payload->'address','city',r.raw_payload->'city','city_raw',r.raw_payload->'city_raw','property_city',r.raw_payload->'property'->'city') AS raw_location_metadata FROM normalized_listings n LEFT JOIN parsed_listings p ON p.id=n.parsed_listing_id LEFT JOIN raw_listings r ON r.id=p.raw_listing_id ORDER BY n.id"""
 total=0
 with c.cursor(name='phase5_snapshot') as cur,gzip.open(out,'wt',encoding='utf8') as f:
  cur.itersize=1000;cur.execute(sql)
  for vals in cur:
   f.write(json.dumps(dict(zip([d.name for d in cur.description],vals)),ensure_ascii=False,default=str)+'\n');total+=1
 assert total==count
 counts={name:c.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in ['raw_listings','parsed_listings','listing_observations']}
 c.rollback()
 result={'transaction_read_only':meta[0],'snapshot':meta[1],'captured_at':meta[2],'normalized_count':count,'max_id':max_id,'normalized_content_fingerprint':fingerprint,'other_table_counts':counts,'input_sha256':digest(out),'baseline_frozen_count':63686,'count_drift':count-63686,'policy':'Current data check is separate from frozen historical comparison; lifecycle observations not treated as normalized rows.'}
 write(B/'validation/current_database_snapshot.json',result)
 print(json.dumps(result))
