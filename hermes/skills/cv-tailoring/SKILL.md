---
name: cv-tailoring
description: Critique and tailor my CV to a job description, truthfully
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [career, cv, resume, job-application, ats]
    category: kaggle-compe
---

# CV Tailoring

Review and tailor the user's CV for a specific role or industry while keeping every statement
true. The user is an Industrial Engineering graduate (Universitas Gadjah Mada) whose identity is:
**Industrial Engineering + Data Analysis + Business Problem Solving + Operations + Process
Improvement + Leadership.** Keep that identity; shift the emphasis per role.

## When to Use
- "Review my CV", "tailor my CV for <job>", "write bullets for <experience>", cover letters.

## Procedure
1. **Collect inputs:** the current CV and, if given, the job description (JD). Check memory
   (USER.md) for the user's background; don't re-ask what is already known.
2. **Analyse the JD first** (if given): top 5-8 competencies, must-have vs nice-to-have,
   recurring keywords, the industry and level. Present this as a short table.
3. **Gap check:** map each competency to real evidence in the CV. Mark: strong / weak /
   missing. For missing evidence, ask the user a specific question; never fill the gap
   by inventing.
4. **Critique honestly:** weak positioning, generic statements, responsibilities without
   outcomes, missing numbers, repetition, overly technical detail, items that don't help this
   role. Recommend what to remove, rewrite, reorder or expand.
5. **Rewrite bullets:** strong action verb + what you did + how (method/tool) + result.
   One line, at most two. Concise, natural English; no buzzwords; credible for a fresh graduate.
   Use JD keywords where they are true (ATS-friendly, no stuffing).
6. **Industry emphasis:**
   - Mining: operations, safety, process improvement, project management, data, complex sites.
   - Consulting: structured problem solving, quantitative analysis, hypotheses, stakeholders,
     actionable recommendations.
   - Banking: analytics, financial understanding (engineering economics), decision making,
     commercial awareness.
   - FMCG: supply chain, demand analysis (thesis on promotional demand shocks), commercial
     thinking, execution.
   - Manufacturing: quality (QMS internship), process improvement, simulation, productivity.
   - Management trainee / graduate programs: leadership (Secretary General, research team
     lead), adaptability, cross-functional work, initiative.
7. **Deliver:** the tailored CV or bullets, then a short list "Information I need to make this
   stronger" (e.g. numbers, scope, outcomes the user hasn't provided).

## Pitfalls
- Inventing achievements, numbers, tools or responsibilities. If a stronger claim needs
  evidence the user hasn't given, ask for it instead.
- Positioning the user narrowly as only a consultant, data scientist or traditional IE.
- Exaggerated corporate language ("spearheaded synergies") or claims unrealistic for a graduate.
- Just rephrasing existing wording without improving positioning or impact.

## Verification
- Every claim in the output traces to something the user actually provided.
- The top third of the CV reflects the JD's top competencies.
