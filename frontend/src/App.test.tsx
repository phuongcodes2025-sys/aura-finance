import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import type { Analysis, EconomicEvent, Profile, ProfileInput } from './api'

const events: EconomicEvent[] = [
  { id: 1, title: 'Inflation up', category: 'Inflation', description: 'Prices rise.' },
  { id: 2, title: 'Interest rate increase', category: 'Interest rates', description: 'Borrowing costs rise.' },
  { id: 3, title: 'Strong jobs report', category: 'Employment', description: 'Hiring strengthens.' },
  { id: 4, title: 'Housing slowdown', category: 'Housing', description: 'Demand slows.' },
]
let aiConfigured = false
let savedProfile: Profile
let requests: { path: string; body: unknown }[]
let failPath = ''

function analysis(eventId: number): Analysis {
  return {
    id: 7, profile: savedProfile, event: events[eventId - 1], createdAt: '2026-01-01',
    assumptions: ['Demo scenarios, not financial advice.'],
    impacts: (['income', 'business', 'investments', 'realEstate'] as const).map(area => ({
      area,
      risk: area === 'income' || savedProfile[
        area === 'business' ? 'businessOwner' : area === 'investments' ? 'investor' : 'propertyOwner'
      ] ? 'moderate' : 'notApplicable',
      summary: `Impact on ${area}`, explanation: 'Conditional economic exposure.',
      considerations: ['Review actual circumstances.'], ruleId: `rule-${area}`,
    })),
  }
}

beforeEach(() => {
  aiConfigured = false
  requests = []
  failPath = ''
  vi.stubGlobal('fetch', vi.fn(async (path: string, options?: RequestInit) => {
    const body: unknown = options?.body ? JSON.parse(String(options.body)) : undefined
    requests.push({ path, body })
    if (path === failPath) return new Response(JSON.stringify({ detail: 'Test service unavailable' }), { status: 503 })
    if (path === '/api/events') return Response.json(events)
    if (path === '/api/health') return Response.json({ status: 'ok', aiConfigured })
    if (path === '/api/profile') {
      savedProfile = { ...body as ProfileInput, id: 3, createdAt: '2026-01-01' }
      return Response.json(savedProfile, { status: 201 })
    }
    if (path === '/api/analyze') {
      const input = body as { eventId: number }
      return Response.json(analysis(input.eventId), { status: 201 })
    }
    if (path === '/api/chat') return Response.json({ answer: 'Rates can raise variable borrowing costs.', source: 'ai' })
    throw new Error(`Unexpected request: ${path}`)
  }))
})

afterEach(() => vi.unstubAllGlobals())

async function useDemo() {
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Use Dallas business owner demo' }))
  return user
}

async function runDemo() {
  const user = await useDemo()
  await user.click(screen.getByRole('button', { name: /Analyze impact/ }))
  await screen.findByRole('heading', { name: 'Ask your copilot' })
  return user
}

describe('the four-feature MVP', () => {
  it('loads four scenarios and requires a valid profile', async () => {
    render(<App />)
    await screen.findByRole('button', { name: /Analyze impact/ })
    expect(screen.getAllByRole('radio')).toHaveLength(4)
    expect(screen.getByRole('button', { name: /Analyze impact/ })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Occupation'), { target: { value: '   ' } })
    expect(screen.getByRole('button', { name: /Analyze impact/ })).toBeDisabled()
  })

  it('saves the demo profile before analysis and shows four impact cards', async () => {
    render(<App />)
    await runDemo()
    expect(screen.getAllByRole('article')).toHaveLength(4)
    expect(requests.find(item => item.path === '/api/profile')?.body).toMatchObject({
      businessOwner: true, investor: true, propertyOwner: true,
    })
    expect(requests.find(item => item.path === '/api/analyze')?.body).toEqual({ userId: 3, eventId: 2 })
    expect(screen.getByRole('button', { name: 'Ask AI' })).toBeDisabled()
    expect(screen.getByText(/AI is unavailable until/)).toBeInTheDocument()
  })

  it('removes stale results when profile or event changes', async () => {
    render(<App />)
    const user = await runDemo()
    await user.click(screen.getByLabelText('Business owner'))
    expect(screen.queryAllByRole('article')).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: /Analyze impact/ }))
    await screen.findByRole('heading', { name: 'Ask your copilot' })
    expect(screen.getByText('Not applicable')).toBeInTheDocument()
    await user.click(screen.getByRole('radio', { name: /Strong jobs report/ }))
    expect(screen.queryAllByRole('article')).toHaveLength(0)
  })

  it('binds follow-up questions to the saved analysis', async () => {
    aiConfigured = true
    render(<App />)
    const user = await runDemo()
    await user.type(screen.getByLabelText('Your question'), 'Why are rates important?')
    await user.click(screen.getByRole('button', { name: 'Ask AI' }))
    expect(await screen.findByText('Rates can raise variable borrowing costs.')).toBeInTheDocument()
    expect(requests.find(item => item.path === '/api/chat')?.body).toEqual({
      analysisId: 7, question: 'Why are rates important?',
    })
  })

  it('shows chat errors instead of fabricated AI answers', async () => {
    aiConfigured = true
    failPath = '/api/chat'
    render(<App />)
    const user = await runDemo()
    await user.type(screen.getByLabelText('Your question'), 'Why?')
    await user.click(screen.getByRole('button', { name: 'Ask AI' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Test service unavailable')
    expect(screen.queryByText('AI-generated explanation')).not.toBeInTheDocument()
  })

  it('does not request analysis if profile creation fails', async () => {
    failPath = '/api/profile'
    render(<App />)
    const user = await useDemo()
    await user.click(screen.getByRole('button', { name: /Analyze impact/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Test service unavailable')
    expect(requests.some(item => item.path === '/api/analyze')).toBe(false)
    expect(screen.queryAllByRole('article')).toHaveLength(0)
  })

  it('allows retry after an initial backend failure', async () => {
    failPath = '/api/events'
    render(<App />)
    const user = userEvent.setup()
    expect(await screen.findByRole('alert')).toHaveTextContent('Test service unavailable')
    failPath = ''
    await user.click(screen.getByRole('button', { name: 'Retry connection' }))
    await waitFor(() => expect(screen.getAllByRole('radio')).toHaveLength(4))
  })
})
