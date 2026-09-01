import { Hono } from "hono";
import { cors } from "hono/cors";
import { cfg } from "./config.js";
import { agentEventToSse } from "./sse.js";
import { runAgent, newSessionId } from "./agent/run.js";
import { createConversation, listConversations, getConversation, deleteConversation, addMessage, updateTitle, belongsToDevice, titleFromMessage, } from "./storage/conversations.js";
import { classifyQueryMode, gateReply, detectLang } from "./agent/gate.js";
import { parseEntities } from "./context/memory.js";
const app = new Hono();
app.use("*", cors({
    origin: cfg.corsOrigins.includes("*") ? "*" : cfg.corsOrigins,
    allowHeaders: ["Content-Type", "X-Device-Id"],
}));
function deviceId(c) {
    const id = c.req.header("X-Device-Id");
    return id?.trim() || null;
}
app.get("/health", (c) => c.json({ status: "ok", runtime: "agent-runtime-ts" }));
app.get("/conversations", (c) => {
    const did = deviceId(c);
    if (!did)
        return c.json({ error: "X-Device-Id required" }, 401);
    return c.json({ conversations: listConversations(did) });
});
app.post("/conversations", async (c) => {
    const did = deviceId(c);
    if (!did)
        return c.json({ error: "X-Device-Id required" }, 401);
    const body = await c.req.json().catch(() => ({}));
    const title = body.title || "New conversation";
    const conv = createConversation(did, title);
    return c.json(conv);
});
app.get("/conversations/:id", (c) => {
    const did = deviceId(c);
    if (!did)
        return c.json({ error: "X-Device-Id required" }, 401);
    const conv = getConversation(c.req.param("id"), did);
    if (!conv)
        return c.json({ error: "Not found" }, 404);
    return c.json(conv);
});
app.delete("/conversations/:id", (c) => {
    const did = deviceId(c);
    if (!did)
        return c.json({ error: "X-Device-Id required" }, 401);
    const ok = deleteConversation(c.req.param("id"), did);
    if (!ok)
        return c.json({ error: "Not found" }, 404);
    return c.json({ ok: true });
});
app.post("/conversations/:id/messages", async (c) => {
    const did = deviceId(c);
    if (!did)
        return c.json({ error: "X-Device-Id required" }, 401);
    const id = c.req.param("id");
    if (!belongsToDevice(id, did))
        return c.json({ error: "Not found" }, 403);
    const body = await c.req.json();
    const role = String(body.role || "user");
    const content = String(body.content || "");
    const meta = body.meta;
    addMessage(id, role, content, meta);
    return c.json({ ok: true });
});
app.post("/classify", async (c) => {
    const body = await c.req.json();
    const message = String(body.message || "");
    const entities = parseEntities(message);
    const mode = classifyQueryMode(message, entities);
    const lang = detectLang(message);
    const routeCollection = mode === "collection";
    return c.json({
        mode,
        entities,
        route_collection: routeCollection,
        reply: gateReply(mode, lang),
    });
});
app.post("/chat", async (c) => {
    const did = deviceId(c);
    if (!did)
        return c.json({ error: "X-Device-Id required" }, 401);
    const body = await c.req.json();
    const message = String(body.message || "");
    const mode = (body.mode === "deep_research" ? "deep_research" : "qa");
    const sessionId = body.session_id || newSessionId();
    let conversationId = body.conversation_id;
    const history = (body.history || []);
    const clarificationResponse = body.clarification_response;
    let userMsg = message.trim();
    if (!userMsg && clarificationResponse) {
        userMsg = clarificationResponse.skip ? "（跳过补充，直接研究）" : "（已补充研究信息）";
    }
    if (conversationId && !belongsToDevice(conversationId, did)) {
        return c.json({ error: "Conversation not found" }, 403);
    }
    let isNew = false;
    if (!conversationId) {
        const conv = createConversation(did, titleFromMessage(userMsg || "Research"));
        conversationId = conv.id;
        isNew = true;
    }
    if (userMsg)
        addMessage(conversationId, "user", userMsg);
    if (isNew && userMsg)
        updateTitle(conversationId, titleFromMessage(userMsg));
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
        async start(controller) {
            let fullAnswer = "";
            let followUps = [];
            try {
                for await (const event of runAgent({
                    message: message || userMsg,
                    sessionId,
                    history,
                    mode,
                    clarificationResponse,
                })) {
                    const sse = agentEventToSse(event);
                    if (sse)
                        controller.enqueue(encoder.encode(sse));
                    if (event.type === "text")
                        fullAnswer += event.content || "";
                    if (event.type === "follow_up_questions")
                        followUps = event.questions || [];
                }
            }
            catch (e) {
                const errSse = agentEventToSse({ type: "error", message: String(e) });
                if (errSse)
                    controller.enqueue(encoder.encode(errSse));
            }
            if (fullAnswer) {
                addMessage(conversationId, "assistant", fullAnswer, {
                    follow_ups: followUps,
                    mode,
                });
            }
            controller.close();
        },
    });
    return new Response(stream, {
        headers: {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            Connection: "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Session-Id": sessionId,
            "X-Conversation-Id": conversationId,
        },
    });
});
export { app };
