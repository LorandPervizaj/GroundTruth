"""Real desktop/mobile journeys against only the loopback immutable QA image."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright,expect
E=Path('C:/Projects/FartEstate/release/readiness/evidence');base='http://127.0.0.1:18765';results=[]
with sync_playwright()as pw:
 browser=pw.chromium.launch()
 for name,width,height in [('desktop',1440,1000),('mobile',375,812)]:
  context=browser.new_context(viewport={'width':width,'height':height});page=context.new_page();errors=[];network=[]
  page.on('pageerror',lambda error:errors.append(str(error)))
  page.on('response',lambda r:network.append({'url':r.url.split(base)[-1],'status':r.status})if r.url.startswith(base)and r.status>=400 else None)
  for path in ['/','/market/neighborhood/ulpiana','/statistics','/compare?n=ulpiana,arberia','/find','/valuate','/rent-yield','/about','/methodology']:
   response=page.goto(base+path,wait_until='domcontentloaded');assert response.status==200,(name,path,response.status)
   expect(page.locator('main')).to_be_visible();page.locator('[data-lang="en"]').first.click();expect(page.locator('html')).to_have_attribute('lang','en')
   page.locator('[data-lang="sq"]').first.click();expect(page.locator('html')).to_have_attribute('lang','sq')
   if path=='/statistics':assert page.evaluate('typeof window.Chart')=='function'
   if path.startswith('/compare'):expect(page.locator('#compare-results')).to_be_visible(timeout=20000)
   if path=='/rent-yield':expect(page.locator('#yield-body tr').first).to_be_visible(timeout=20000)
   if path=='/find':
    page.locator('#find-submit').click();expect(page.locator('#find-results:not(.hidden), #find-empty:not(.hidden)')).to_be_visible(timeout=30000)
   if path=='/valuate':
    page.locator('#neighborhood-input').fill('Ulpiana');page.locator('.metrik-search-item').filter(has_text='Ulpiana').first.click();page.locator('#submit-btn').click();expect(page.locator('#results')).to_be_visible(timeout=30000)
   assert not page.evaluate('document.documentElement.scrollWidth > document.documentElement.clientWidth'),(name,path,'horizontal overflow')
   if path in ['/','/statistics','/valuate']:page.screenshot(path=str(E/f'{name}-{path.strip("/")or"home"}.png'),full_page=True)
   results.append({'viewport':name,'path':path,'status':'PASS','languages':['en','sq']})
  assert not errors,errors
  (E/f'{name}-browser-events.json').write_text(json.dumps({'page_errors':errors,'http_errors':network},indent=2),encoding='utf8')
  context.close()
 browser.close()
(E/'browser-journeys.json').write_text(json.dumps({'journeys':results,'passed':len(results),'browser':'Chromium','origin':base,'production_tested':False,'image_digest':json.loads((E/'release-identity.json').read_text())['image_manifest_digest']},indent=2),encoding='utf8');print(json.dumps({'passed':len(results)}))
