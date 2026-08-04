/** Small fetch helper with timeout + JSON/text */

export class HttpError extends Error {
  constructor(
    message: string,
    readonly status?: number,
    readonly url?: string,
  ) {
    super(message)
    this.name = "HttpError"
  }
}

export async function fetchText(
  url: string,
  opts: { timeoutMs?: number; headers?: Record<string, string>; accept?: string } = {},
): Promise<string> {
  const timeoutMs = opts.timeoutMs ?? 20_000
  const ctrl = new AbortController()
  const t = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const res = await fetch(url, {
      signal: ctrl.signal,
      redirect: "follow",
      headers: {
        "User-Agent": "qPTM-CollectionAgent/0.1 (literature mining; mailto:local)",
        Accept: opts.accept ?? "*/*",
        ...opts.headers,
      },
    })
    if (!res.ok) throw new HttpError(`HTTP ${res.status}`, res.status, url)
    return await res.text()
  } finally {
    clearTimeout(t)
  }
}

export async function fetchJson<T>(
  url: string,
  opts: { timeoutMs?: number; headers?: Record<string, string> } = {},
): Promise<T> {
  const text = await fetchText(url, {
    ...opts,
    accept: "application/json",
    headers: { Accept: "application/json", ...opts.headers },
  })
  return JSON.parse(text) as T
}

export async function fetchBinary(
  url: string,
  opts: { timeoutMs?: number; headers?: Record<string, string>; accept?: string } = {},
): Promise<{ buffer: Buffer; contentType: string | null }> {
  const timeoutMs = opts.timeoutMs ?? 60_000
  const ctrl = new AbortController()
  const t = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const res = await fetch(url, {
      signal: ctrl.signal,
      redirect: "follow",
      headers: {
        "User-Agent": "qPTM-CollectionAgent/0.1 (literature mining; mailto:local)",
        Accept: opts.accept ?? "*/*",
        ...opts.headers,
      },
    })
    if (!res.ok) throw new HttpError(`HTTP ${res.status}`, res.status, url)
    const ab = await res.arrayBuffer()
    return {
      buffer: Buffer.from(ab),
      contentType: res.headers.get("content-type"),
    }
  } finally {
    clearTimeout(t)
  }
}
