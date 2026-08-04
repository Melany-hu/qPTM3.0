/**
 * iProX public web APIs — https://www.iprox.cn/page/helpApi.html
 *
 * Documented JSONP endpoints (no login required):
 *   projectFileList/getProjectDataFileByProjectId.jsonp
 *   projectFileList/getProjectDataFileByDay|Month|Year.jsonp
 *
 * ProteomeXchange XML for an IPX project (public HTTP):
 *   http://download.iprox.org/{IPX}/PX_{IPX}.xml
 *
 * Bulk download via Aspera (account required):
 *   username@download.iprox.org:/data/iprox/{IPX}
 */
import { fetchJson, fetchText } from "../stage2/http.js"

const IPROX_BASE = "https://www.iprox.cn"
const IPROX_DOWNLOAD_HTTP = "http://download.iprox.org"
const IPROX_DOWNLOAD_HTTP_CN = "http://download.iprox.cn"

export interface IproxApiResponse<T> {
  code: number
  message: string
  data: T
}

export function iproxPxXmlUrl(ipx: string, mirror: "org" | "cn" = "org"): string {
  const id = ipx.toUpperCase()
  const host = mirror === "cn" ? IPROX_DOWNLOAD_HTTP_CN : IPROX_DOWNLOAD_HTTP
  return `${host}/${id}/PX_${id}.xml`
}

/** Aspera source path documented on helpApi.html */
export function iproxAsperaSource(ipx: string, username: string): string {
  return `${username}@download.iprox.org:/data/iprox/${ipx.toUpperCase()}`
}

async function iproxJsonp<T>(endpoint: string, params: Record<string, string>): Promise<IproxApiResponse<T>> {
  const qs = new URLSearchParams(params).toString()
  const url = `${IPROX_BASE}/projectFileList/${endpoint}?${qs}`
  return fetchJson<IproxApiResponse<T>>(url, { timeoutMs: 30_000 })
}

/** Check whether iProX knows this project (code 200) or has no public data (222). */
export async function iproxGetProject(ipx: string): Promise<IproxApiResponse<string>> {
  return iproxJsonp<string>("getProjectDataFileByProjectId.jsonp", {
    projectId: ipx.toUpperCase(),
  })
}

export async function iproxListProjectsByDay(date: string): Promise<IproxApiResponse<string[]>> {
  return iproxJsonp<string[]>("getProjectDataFileByDay.jsonp", { date })
}

export async function iproxListProjectsByMonth(date: string): Promise<IproxApiResponse<string[]>> {
  return iproxJsonp<string[]>("getProjectDataFileByMonth.jsonp", { date })
}

export async function iproxListProjectsByYear(date: string): Promise<IproxApiResponse<string[]>> {
  return iproxJsonp<string[]>("getProjectDataFileByYear.jsonp", { date })
}

/** Download ProteomeXchange XML for an IPX accession (tries .org then .cn mirror). */
export async function fetchIproxPxXml(ipx: string): Promise<{ xml: string; url: string }> {
  const id = ipx.toUpperCase()
  let lastErr: unknown
  for (const mirror of ["org", "cn"] as const) {
    const url = iproxPxXmlUrl(id, mirror)
    try {
      const xml = await fetchText(url, {
        timeoutMs: 60_000,
        accept: "application/xml,text/xml,*/*",
      })
      if (xml.includes("<ProteomeXchangeDataset")) return { xml, url }
      lastErr = new Error(`Not ProteomeXchange XML from ${url}`)
    } catch (err) {
      lastErr = err
    }
  }
  throw lastErr instanceof Error ? lastErr : new Error(`Cannot fetch iProX XML for ${id}`)
}

/** Extract mirrored PXD accession from a ProteomeXchange XML string, if present. */
export function parsePxdFromPxXml(xml: string): string | undefined {
  const m = xml.match(/\b(PXD\d{5,})\b/i)
  return m ? m[1].toUpperCase() : undefined
}

export interface IproxSubprojectFile {
  fileId: string
  fileName: string
  filePath: string
  fileType?: string
}

export interface IproxSubprojectInfo {
  subprojectId: string
  projectId: string
  proteomexchangeId?: string | null
  subtitleEn?: string | null
}

interface IproxSubprojectApiData {
  subProjectInfo?: IproxSubprojectInfo
  subdatafilesInfo?: IproxSubprojectFile[]
}

/** Convert iProX nginx filePath to public HTTP download URL. */
export function iproxFilePathToHttpUrl(filePath: string, mirror: "org" | "cn" = "org"): string {
  const host = mirror === "cn" ? IPROX_DOWNLOAD_HTTP_CN : IPROX_DOWNLOAD_HTTP
  let rel = filePath.trim()
  rel = rel.replace(/^\/usr\/local\/nginx\/data\//i, "")
  rel = rel.replace(/^\\usr\\local\\nginx\\data\\/i, "")
  rel = rel.replace(/\\/g, "/")
  return `${host}/${rel}`
}

/**
 * Fetch subproject metadata + files via PMD009Controller (used by subproject.html).
 * @see https://www.iprox.cn/page/subproject.html?id=IPX…
 */
export async function iproxFetchSubproject(
  subProjectId: string,
): Promise<{
  subproject: IproxSubprojectInfo
  parentProjectId: string
  files: IproxSubprojectFile[]
  urls: string[]
} | null> {
  const id = subProjectId.toUpperCase()
  const res = await fetch(`${IPROX_BASE}/PMD009Controller/findBySubProjectId.jsonp`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      "User-Agent": "qPTM-CollectionAgent/0.1 (literature mining)",
    },
    body: `subProjectId=${encodeURIComponent(id)}&language=en`,
    signal: AbortSignal.timeout(30_000),
  })
  if (!res.ok) return null
  const json = (await res.json()) as { data?: IproxSubprojectApiData }
  const sub = json.data?.subProjectInfo
  const files = json.data?.subdatafilesInfo ?? []
  if (!sub?.subprojectId || sub.subprojectId.toUpperCase() !== id) return null
  if (files.length === 0) return null

  const parentProjectId = (sub.projectId ?? "").toUpperCase()
  const urls = [
    ...new Set(
      files
        .map((f) => iproxFilePathToHttpUrl(f.filePath))
        .filter((u) => u.startsWith("http")),
    ),
  ]
  return { subproject: sub, parentProjectId, files, urls }
}
