import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { spawn } from "node:child_process";
import { cfg } from "../config.js";
let qptmClient = null;
let biomcpClient = null;
let qptmInitPromise = null;
let biomcpInitPromise = null;
const MCP_CONNECT_TIMEOUT_MS = Number(process.env.MCP_CONNECT_TIMEOUT_MS || 8000);
async function connectStdio(name, command, args, cwd) {
    try {
        const transport = new StdioClientTransport({
            command,
            args,
            cwd,
            stderr: "pipe",
        });
        const client = new Client({ name: `qptm-agent-${name}`, version: "1.0.0" });
        await client.connect(transport);
        return { name, client, transport };
    }
    catch (e) {
        console.warn(`MCP ${name} connect failed:`, e);
        return null;
    }
}
async function connectStdioWithTimeout(name, command, args, cwd) {
    let timer;
    try {
        return await Promise.race([
            connectStdio(name, command, args, cwd),
            new Promise((resolve) => {
                timer = setTimeout(() => {
                    console.warn(`MCP ${name} connect timed out after ${MCP_CONNECT_TIMEOUT_MS}ms`);
                    resolve(null);
                }, MCP_CONNECT_TIMEOUT_MS);
            }),
        ]);
    }
    finally {
        if (timer)
            clearTimeout(timer);
    }
}
/** Connect qPTM stdio MCP only — never blocks on BioMCP. */
export async function initQptmMcp() {
    if (qptmInitPromise)
        return qptmInitPromise;
    qptmInitPromise = (async () => {
        qptmClient = await connectStdioWithTimeout("qptm", cfg.qptmMcpCommand, cfg.qptmMcpArgs, cfg.qptmMcpCwd);
    })();
    return qptmInitPromise;
}
/** Lazy BioMCP — optional; failures/timeouts do not block chat. */
async function initBiomcpMcp() {
    if (biomcpClient)
        return biomcpClient;
    if (biomcpInitPromise)
        return biomcpInitPromise;
    biomcpInitPromise = connectStdioWithTimeout("biomcp", cfg.biomcpCommand, cfg.biomcpArgs);
    biomcpClient = await biomcpInitPromise;
    return biomcpClient;
}
/** @deprecated Use initQptmMcp — kept for callers that only need qPTM tools. */
export async function initMcpClients() {
    await initQptmMcp();
}
async function ensureQptmMcp() {
    await initQptmMcp();
}
async function ensureBiomcpMcp() {
    return initBiomcpMcp();
}
export async function readQptmResource(uri) {
    await ensureQptmMcp();
    if (!qptmClient)
        return "";
    try {
        const res = await qptmClient.client.readResource({ uri });
        return res.contents
            .map((c) => ("text" in c ? c.text : "") || "")
            .join("\n");
    }
    catch {
        return "";
    }
}
export async function callQptmTool(toolName, args) {
    await ensureQptmMcp();
    if (!qptmClient) {
        return { success: false, summary: "qPTM MCP not connected", data: null };
    }
    try {
        const result = await qptmClient.client.callTool({ name: toolName, arguments: args });
        const content = (result.content || []);
        const text = content
            .map((c) => c.text || "")
            .filter(Boolean)
            .join("\n");
        let parsed = {};
        try {
            parsed = JSON.parse(text);
        }
        catch {
            parsed = { raw: text };
        }
        return {
            success: !result.isError,
            summary: String(parsed.summary || text.slice(0, 400)),
            data: parsed.data ?? parsed,
        };
    }
    catch (e) {
        return { success: false, summary: String(e), data: null };
    }
}
export async function callBiomcp(command, args = []) {
    const client = await ensureBiomcpMcp();
    if (!client) {
        return await fallbackBiomcpCli(command, args);
    }
    try {
        const result = await client.client.callTool({
            name: "biomcp",
            arguments: { command, args },
        });
        const content = (result.content || []);
        return content.map((c) => c.text || "").join("\n").slice(0, 8000);
    }
    catch (e) {
        return `BioMCP error: ${e}`;
    }
}
async function fallbackBiomcpCli(command, args) {
    return new Promise((resolve) => {
        const child = spawn(cfg.biomcpCommand, [command, ...args], { timeout: 30000 });
        let out = "";
        child.stdout.on("data", (d) => (out += d));
        child.stderr.on("data", (d) => (out += d));
        child.on("close", () => resolve(out.slice(0, 8000)));
        child.on("error", () => resolve("BioMCP CLI not available"));
    });
}
export async function biomcpSearchArticle(query) {
    return callBiomcp("search", ["article", query]);
}
export async function biomcpGetArticle(id) {
    return callBiomcp("get", ["article", id]);
}
export async function webSearch(query) {
    if (!cfg.tavilyApiKey) {
        return await biomcpSearchArticle(query);
    }
    const controller = new AbortController();
    const t = setTimeout(() => controller.abort(), cfg.webSearchTimeoutMs);
    try {
        const res = await fetch("https://api.tavily.com/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                api_key: cfg.tavilyApiKey,
                query,
                max_results: 5,
                search_depth: "basic",
            }),
            signal: controller.signal,
        });
        const data = (await res.json());
        return (data.results || [])
            .map((r) => `${r.title}\n${r.content}\n${r.url}`)
            .join("\n---\n")
            .slice(0, 4000);
    }
    catch (e) {
        return `Web search failed: ${e}`;
    }
    finally {
        clearTimeout(t);
    }
}
