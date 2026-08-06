import { chromium } from 'playwright'

const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' })
const p = await b.newPage({ viewport: { width: 1440, height: 900 } })
const errs = []
p.on('pageerror', (e) => errs.push('PAGEERROR: ' + e.message))
p.on('console', (m) => m.type() === 'error' && errs.push(m.text()))
const log = []

await p.goto('http://localhost:4173/', { waitUntil: 'domcontentloaded' })
await p.evaluate(() => localStorage.clear())

await p.goto('http://localhost:4173/#/review', { waitUntil: 'networkidle' })
await p.waitForFunction(() => {
  const v = document.querySelector('video')
  return v && v.readyState >= 2
}, { timeout: 15000 })
log.push('video loaded')

const tc = () => p.getByLabel('Current timecode').innerText()

// 1. Frame stepping must move exactly one frame at a time (25 fps clip).
await p.getByLabel('Next frame').click()
await p.getByLabel('Next frame').click()
await p.getByLabel('Next frame').click()
log.push('after 3x next frame: ' + (await tc()))
await p.getByLabel('Previous frame').click()
log.push('after 1x prev frame: ' + (await tc()))

// 2. Clicking a note's timecode must seek to that exact frame.
await p.getByRole('button', { name: /Jump to note at/ }).first().click()
await p.waitForTimeout(250)
log.push('after clicking first timeline marker: ' + (await tc()))
await p.screenshot({ path: 'screenshots/review.png' })

// 3. A drawn region + note must persist and appear in the rail.
await p.getByRole('button', { name: 'Draw' }).click()
const stage = await p.locator('video').boundingBox()
await p.mouse.move(stage.x + 260, stage.y + 140)
await p.mouse.down()
await p.mouse.move(stage.x + 520, stage.y + 330, { steps: 12 })
await p.mouse.up()
log.push('area marked: ' + (await p.getByText('area marked').isVisible()))
const mark = await tc()
await p.getByLabel('Leave a note on this frame').fill('Sky is blown out in this corner — pull the highlights.')
await p.getByRole('button', { name: 'Add note' }).click()
await p.waitForTimeout(300)
log.push('note in rail: ' + (await p.getByText('Sky is blown out').isVisible()))
log.push('note pinned at: ' + mark)
await p.screenshot({ path: 'screenshots/review-annotated.png' })

// 4. Resolve must move it out of the open count.
const openBefore = await p.getByText(/\d+ open/).innerText()
await p.getByLabel('Resolve note').first().click()
await p.waitForTimeout(250)
log.push(`open count ${openBefore} -> ${await p.getByText(/\d+ open/).innerText()}`)

// 5. Version switching must swap both the source and the note set.
await p.getByRole('button', { name: 'v2', exact: true }).click()
await p.waitForTimeout(600)
log.push('v2 source: ' + (await p.locator('video source').first().getAttribute('src')))
log.push('v2 shows only v2 notes: ' +
  (await p.getByText('Match the grade').isVisible()) + ' / v1 note gone: ' +
  ((await p.getByText('Sky is blown out').count()) === 0))
await p.getByRole('button', { name: 'v1', exact: true }).click()
await p.waitForTimeout(600)
log.push('back on v1 source: ' + (await p.locator('video source').first().getAttribute('src')))

// 6. Request changes must reach the card and the Inbox.
await p.getByRole('button', { name: 'Request changes' }).click()
await p.waitForTimeout(300)
await p.goto('http://localhost:4173/#/inbox', { waitUntil: 'networkidle' })
await p.waitForTimeout(300)
log.push('review decision in Inbox: ' + (await p.getByText(/Changes requested on Tristan/).first().isVisible()))

await p.goto('http://localhost:4173/#/boards?card=card-2', { waitUntil: 'networkidle' })
await p.waitForTimeout(400)
log.push('decision commented on card: ' + (await p.getByText(/Changes requested on Tristan/).first().isVisible()))
log.push('Review button on card: ' + (await p.getByRole('link', { name: 'Review' }).first().isVisible()))
await p.screenshot({ path: 'screenshots/review-card.png' })

// 7. Persistence.
await p.goto('http://localhost:4173/#/review', { waitUntil: 'networkidle' })
await p.waitForTimeout(500)
log.push('drawn note survived reload: ' + (await p.getByText('Sky is blown out').count() > 0))

await b.close()
console.log(log.join('\n'))
console.log(errs.length ? '\nERRORS:\n' + errs.join('\n') : '\nNO CONSOLE ERRORS')
