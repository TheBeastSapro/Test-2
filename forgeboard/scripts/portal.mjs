import { chromium } from 'playwright'

const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' })
const p = await b.newPage({ viewport: { width: 1440, height: 900 } })
const errs = []
p.on('pageerror', (e) => errs.push('PAGEERROR: ' + e.message))
p.on('console', (m) => m.type() === 'error' && errs.push(m.text()))

await p.goto('http://localhost:4174/', { waitUntil: 'domcontentloaded' })
await p.evaluate(() => localStorage.clear())

await p.goto('http://localhost:4174/#/portal', { waitUntil: 'networkidle' })
await p.waitForTimeout(400)
await p.screenshot({ path: 'screenshots/portal.png' })

await p.getByRole('button', { name: 'Approve' }).first().click()
await p.waitForTimeout(400)
console.log('approved label shown:', await p.getByText('Approved', { exact: true }).first().isVisible())

await p.goto('http://localhost:4174/#/inbox', { waitUntil: 'networkidle' })
await p.waitForTimeout(300)
console.log('client approval reached Inbox:', await p.getByText(/Client approved KB-/).first().isVisible())
await p.screenshot({ path: 'screenshots/portal-inbox.png' })

await b.close()
console.log(errs.length ? 'ERRORS:\n' + errs.join('\n') : 'NO CONSOLE ERRORS')
