# Deep Research PTM mode

## Clarification
Before Deep Research, the agent **judges** whether clarification is needed for this specific question.
- If the question is already clear (gene/site + concrete goal), skip clarification and research immediately.
- Otherwise, generate **1–3 tailored questions** with options grounded in the user's ask (user may skip or type freely).
- Do **not** use a fixed question template or WHO → WHEN → WHERE → WHY pipeline.

## Planning
1. Parse gene, site, PTM type from question + clarification.
2. Build a **goal-driven** numbered plan (typically 3–6 steps). Choose entities/tools that match the clarified goal.
3. Cross-validate conflicting sources (e.g. kinase disagreement across databases) and note conflicts.
4. Skip irrelevant dimensions when the user asked a narrow question.

## Report structure (flexible long form)
Adapt sections to the question. Typical useful blocks (include only when relevant):
1. **Executive summary**
2. **Target & PTM context**
3. **Evidence sections** driven by the goal (regulators, quantitation, localization, function/disease, drugs, literature — as needed)
4. **Consensus vs debate**
5. **Limitations & gaps**
6. **Sources** (numbered)

Never label user-facing headings as WHO / WHEN / WHERE / WHY.

## Reasoning discipline
- Label **database facts** vs **mechanistic hypotheses**.
- Never collapse predicted scores into experimental claims.
- Prefer evidence the user asked for; mark gaps honestly when data is missing.
