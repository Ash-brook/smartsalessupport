// Typed client for the SmartSupport API. URLs are relative; Vite proxies /api to :8000.

export interface QueueItem {
  draft_id: string
  email_id: string
  customer_name: string
  subject: string
  intent: string | null
  confidence: number | null
  received_at: string
  status: string
  requires_human_review: boolean
  flags: string[]
}

export interface QueueResponse {
  items: QueueItem[]
  page: number
  page_size: number
  total: number
}

export interface OrderContext {
  order_id: string
  product_name: string
  sku: string
  status: string
  order_date: string
  estimated_delivery_date: string | null
  tracking_number: string | null
  amount_usd: number
  payment_status: string
}

export interface DraftDetail {
  draft_id: string
  subject: string
  body: string
  final_body: string | null
  intent: string | null
  confidence: number | null
  reasoning: string | null
  requires_human_review: boolean
  flags: string[]
  status: string
  model_used: string | null
}

export interface DetailResponse {
  draft: DraftDetail
  email: {
    email_id: string
    subject: string
    body_text: string
    received_at: string
    customer_name: string
    customer_email: string
  }
  context: {
    customer: {
      customer_id: string
      name: string
      email: string
      account_tier: string
      country: string
      lifetime_value_usd: number
      registration_date: string
    }
    recent_orders: OrderContext[]
    open_tickets: { email_id: string; subject: string; status: string; received_at: string }[]
  }
}

export interface Metrics {
  total_emails: number
  processed: number
  auto_approved: number
  hitl: number
  pending: number
  sent: number
  rejected: number
  zero_touch_rate: number
  hitl_rate: number
  edit_rate: number
  rejection_rate: number
  category_breakdown: { intent: string; count: number }[]
  audit_log: {
    timestamp: string
    action: string
    agent_id: string | null
    customer_name: string
    subject: string
  }[]
  top_rejection_reasons: { reason: string; count: number }[]
}

export type Action = 'approve' | 'edit' | 'reject'

async function http<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error(detail.detail ?? `Request failed: ${res.status}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  queue: (status = 'pending', page = 1, pageSize = 50) =>
    http<QueueResponse>(`/api/v1/drafts?status=${status}&page=${page}&page_size=${pageSize}`),

  detail: (draftId: string) => http<DetailResponse>(`/api/v1/drafts/${draftId}`),

  act: (
    draftId: string,
    body: { action: Action; edited_body?: string; rejection_reason?: string; agent_id?: string },
  ) =>
    http<{ draft_id: string; status: string; audit_event_id: string }>(
      `/api/v1/drafts/${draftId}/action`,
      { method: 'PATCH', body: JSON.stringify(body) },
    ),

  metrics: () => http<Metrics>('/api/v1/metrics'),
}
