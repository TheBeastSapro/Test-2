import { chromium } from 'playwright'
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' })
const p = await b.newPage({ viewport: { width: 1440, height: 900 } })
const errs = []
p.on('pageerror', e => errs.push('PAGEERROR: ' + e.message))
p.on('console', m => m.type() === 'error' && errs.push(m.text()))
const log = []

await p.goto('http://localhost:4173/', { waitUntil: 'domcontentloaded' })
await p.evaluate(() => localStorage.clear())

await p.goto('http://localhost:4173/#/kloudie', { waitUntil: 'networkidle' })

// 1. Ask kloudie to build a board.
await p.getByLabel('Message kloudie').fill('make a board where I can manage this channel')
await p.getByLabel('Send').click()
await p.getByRole('button', { name: 'Approve' }).waitFor({ timeout: 8000 })
log.push('proposal rendered')
const creditsBefore = await p.locator('nav >> text=/credits/').last().innerText()

// 2. Approve it.
await p.getByRole('button', { name: 'Approve' }).click()
await p.waitForTimeout(400)
log.push('approved: ' + (await p.locator('text=Applied to the workspace').count()) + ' confirmation(s)')
await p.screenshot({ path: 'screenshots/flow-1-approved.png' })

// 3. The board must now exist in the Boards app.
await p.goto('http://localhost:4173/#/boards', { waitUntil: 'networkidle' })
await p.waitForTimeout(400)
const boardBtn = p.getByRole('button', { name: 'Travel Documentary Channel 2' })
log.push('new board button visible: ' + await boardBtn.isVisible())
await boardBtn.click()
await p.waitForTimeout(300)
const cardVisible = await p.getByText('How People Live in Bermuda', { exact: true }).first().isVisible()
log.push('agent-created card on new board: ' + cardVisible)
await p.screenshot({ path: 'screenshots/flow-2-board.png' })

// 4. Credits must have been spent.
await p.goto('http://localhost:4173/#/kloudie', { waitUntil: 'networkidle' })
const creditsAfter = await p.locator('nav >> text=/credits/').last().innerText()
log.push(`credits ${creditsBefore.trim()} -> ${creditsAfter.trim()}`)

// 5. Playground generation must land in Library.
await p.goto('http://localhost:4173/#/kloudie/playground', { waitUntil: 'networkidle' })
await p.getByLabel('Text to Speech prompt').fill('This is Bermuda, a lonely rock in the middle of the ocean.')
await p.getByRole('button', { name: 'Generate' }).click()
await p.getByText('Saved to Library').waitFor({ timeout: 8000 })
log.push('playground generated + saved')
await p.screenshot({ path: 'screenshots/flow-3-playground.png' })
await p.goto('http://localhost:4173/#/kloudie/library', { waitUntil: 'networkidle' })
log.push('library shows new creation: ' + await p.getByText('This is Bermuda, a lonely rock').first().isVisible())

// 6. Economy: pay a pending payout, invoice must generate.
await p.goto('http://localhost:4173/#/pay', { waitUntil: 'networkidle' })
const before = await p.getByText('Pay now').count()
await p.getByRole('button', { name: 'Pay now' }).first().click()
await p.waitForTimeout(300)
const after = await p.getByText('Pay now').count()
log.push(`payouts pending ${before} -> ${after}, invoices on page: ${await p.locator('text=/INV-/').count()}`)
await p.screenshot({ path: 'screenshots/flow-4-economy.png' })

// 7. Persistence across reload.
await p.reload({ waitUntil: 'networkidle' })
log.push('after reload pending payouts: ' + await p.getByText('Pay now').count())

await b.close()
console.log(log.join('\n'))
console.log(errs.length ? '\nERRORS:\n' + errs.join('\n') : '\nNO CONSOLE ERRORS')
