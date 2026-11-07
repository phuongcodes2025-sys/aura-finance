export type IncomeRange = 'under-30k' | '30k-60k' | '60k-100k' | 'over-100k'

export interface ProfileInput {
  name: string
  occupation: string
  incomeRange: IncomeRange
  businessOwner: boolean
  investor: boolean
  propertyOwner: boolean
}

export interface Profile extends ProfileInput {
  id: number
  createdAt: string
}

export interface EconomicEvent {
  id: number
  title: string
  category: string
  description: string
}

export interface Impact {
  area: 'income' | 'business' | 'investments' | 'realEstate'
  risk: 'low' | 'moderate' | 'high' | 'notApplicable'
  summary: string
  explanation: string
  considerations: string[]
  ruleId: string | null
}

export interface Analysis {
  id: number
  profile: Profile
  event: EconomicEvent
  impacts: Impact[]
  assumptions: string[]
  createdAt: string
}

export interface Health {
  status: 'ok'
  aiConfigured: boolean
}

export interface ChatResponse {
  answer: string
  source: 'ai'
}

function errorDetail(body: unknown): string | undefined {
  if (typeof body !== 'object' || body === null || !('detail' in body)) return
  if (typeof body.detail === 'string') return body.detail
  if (Array.isArray(body.detail)) return 'Some inputs are invalid. Please check your profile and question.'
}

export async function request<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new Error('Cannot reach the backend. Start FastAPI on port 8000 and try again.')
  }
  let data: unknown
  try {
    data = await response.json()
  } catch {
    throw new Error('The backend returned an unreadable response. Check that FastAPI is running.')
  }
  if (!response.ok) throw new Error(errorDetail(data) ?? `Request failed (${response.status}). Please try again.`)
  return data as T
}

export function message(error: unknown): string {
  return error instanceof Error ? error.message : 'An unexpected error occurred. Please try again.'
}
