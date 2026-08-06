import { chromium } from 'playwright'
const routes = [
  ['dashboard', '#/'],
  ['boards', '#/boards'],
  ['calendar', '#/calendar'],
  ['chat', '#/chat'],
  ['review', '#/review'],
  ['pay', '#/pay'],
  ['invoices', '#/invoices'],
  ['drive', '#/drive'],
  ['inbox', '#/inbox'],
  ['portal', '#/portal'],
  ['kloudie-chat', '#/kloudie'],
  ['kloudie-brain', '#/kloudie/brain'],
  ['kloudie-playground', '#/kloudie/playground'],
  ['kloudie-library', '#/kloudie/library'],
  ['kloudie-automations', '#/kloudie/automations'],
]
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' })
const p = await b.newPage({ viewport: { width: 1440, height: 900 } })
const errors = []
p.on('console', m => m.type() === 'error' && errors.push(m.text()))
p.on('pageerror', e => errors.push('PAGEERROR: ' + e.message))
for (const [name, hash] of routes) {
  await p.goto('http://localhost:4173/' + hash, { waitUntil: 'networkidle' })
  await p.waitForTimeout(350)
  await p.screenshot({ path: `screenshots/${name}.png` })
}
await b.close()
console.log(errors.length ? 'ERRORS:\n' + errors.join('\n') : 'NO CONSOLE ERRORS')
