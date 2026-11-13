#!/usr/bin/env bash
# Install the skills Collective Brain hosts on collectivebrain.de/en/skills/ into your own Claude skills folder.
# They are free to use but carry no license to republish, so they are not stored in this repository.
# Each line is the install command the site gives for that skill. Read a skill before relying on it.
#
#   bash scripts/install_collectivebrain_skills.sh                 # all of them, into ~/.claude/skills
#   bash scripts/install_collectivebrain_skills.sh figma-to-code   # only the named ones
#   SKILLS_DIR=.claude/skills bash scripts/install_collectivebrain_skills.sh ...   # into this project instead
set -euo pipefail
DIR="${SKILLS_DIR:-$HOME/.claude/skills}"
declare -A URL=(
  [brand-voice-enforcement]="https://collectivebrain.de/en/skills/brand-voice-enforcement/SKILL.md"
  [brand-voice-guideline-generation]="https://collectivebrain.de/en/skills/brand-voice-guideline-generation/SKILL.md"
  [brand-voice-discover-brand]="https://collectivebrain.de/en/skills/brand-voice-discover-brand/SKILL.md"
  [design-design-critique]="https://collectivebrain.de/en/skills/design-design-critique/SKILL.md"
  [design-accessibility-review]="https://collectivebrain.de/en/skills/design-accessibility-review/SKILL.md"
  [design-ux-copy]="https://collectivebrain.de/en/skills/design-ux-copy/SKILL.md"
  [design-research-synthesis]="https://collectivebrain.de/en/skills/design-research-synthesis/SKILL.md"
  [design-design-handoff]="https://collectivebrain.de/en/skills/design-design-handoff/SKILL.md"
  [design-design-system]="https://collectivebrain.de/en/skills/design-design-system/SKILL.md"
  [design-user-research]="https://collectivebrain.de/en/skills/design-user-research/SKILL.md"
  [marketing-campaign-plan]="https://collectivebrain.de/en/skills/marketing-campaign-plan/SKILL.md"
  [marketing-content-creation]="https://collectivebrain.de/en/skills/marketing-content-creation/SKILL.md"
  [marketing-email-sequence]="https://collectivebrain.de/en/skills/marketing-email-sequence/SKILL.md"
  [marketing-seo-audit]="https://collectivebrain.de/en/skills/marketing-seo-audit/SKILL.md"
  [marketing-competitive-brief]="https://collectivebrain.de/en/skills/marketing-competitive-brief/SKILL.md"
  [marketing-performance-report]="https://collectivebrain.de/en/skills/marketing-performance-report/SKILL.md"
  [marketing-brand-review]="https://collectivebrain.de/en/skills/marketing-brand-review/SKILL.md"
  [anthropic-divi-edit]="https://collectivebrain.de/en/skills/anthropic-divi-edit/SKILL.md"
  [anthropic-frontend-design]="https://collectivebrain.de/en/skills/anthropic-frontend-design/SKILL.md"
  [vercel-web-design-guidelines]="https://collectivebrain.de/en/skills/vercel-web-design-guidelines/SKILL.md"
  [vercel-react-best-practices]="https://collectivebrain.de/en/skills/vercel-react-best-practices/SKILL.md"
  [figma-to-code]="https://collectivebrain.de/en/skills/figma-to-code/SKILL.md"
  [theme-factory]="https://collectivebrain.de/en/skills/theme-factory/SKILL.md"
  [imagegen-frontend-mobile]="https://collectivebrain.de/en/skills/imagegen-frontend-mobile/SKILL.md"
  [brandkit]="https://collectivebrain.de/en/skills/brandkit/SKILL.md"
  [website-builder]="https://collectivebrain.de/en/skills/website-builder/SKILL.md"
  [ai-marketing-team]="https://collectivebrain.de/en/skills/ai-marketing-team/SKILL.md"
  [google-ads-analyzer]="https://collectivebrain.de/en/skills/google-ads-analyzer/SKILL.md"
  [keyword-strategy-planner]="https://collectivebrain.de/en/skills/keyword-strategy-planner/SKILL.md"
  [ux-research-interview-kit]="https://collectivebrain.de/en/skills/ux-research-interview-kit/SKILL.md"
  [ux-flow-wireframer]="https://collectivebrain.de/en/skills/ux-flow-wireframer/SKILL.md"
  [ux-copy-refiner]="https://collectivebrain.de/en/skills/ux-copy-refiner/SKILL.md"
  [persona-workshop-facilitator]="https://collectivebrain.de/en/skills/persona-workshop-facilitator/SKILL.md"
  [b2b-value-proposition-mapper]="https://collectivebrain.de/en/skills/b2b-value-proposition-mapper/SKILL.md"
  [sales-enablement-pack]="https://collectivebrain.de/en/skills/sales-enablement-pack/SKILL.md"
  [founder-pitch-deck-coach]="https://collectivebrain.de/en/skills/founder-pitch-deck-coach/SKILL.md"
  [notion-ops-connector]="https://collectivebrain.de/en/skills/notion-ops-connector/SKILL.md"
  [vopixsounds]="https://collectivebrain.de/skills/vopixsounds/SKILL.md"
  [algorithmic-art]="https://collectivebrain.de/en/skills/algorithmic-art/SKILL.md"
  [claude-api]="https://collectivebrain.de/en/skills/claude-api/SKILL.md"
  [doc-coauthoring]="https://collectivebrain.de/en/skills/doc-coauthoring/SKILL.md"
  [internal-comms]="https://collectivebrain.de/en/skills/internal-comms/SKILL.md"
  [mcp-builder]="https://collectivebrain.de/en/skills/mcp-builder/SKILL.md"
  [github-actions-sparen]="https://collectivebrain.de/en/skills/github-actions-sparen/SKILL.md"
  [seo-strategie-roadmap]="https://collectivebrain.de/en/skills/seo-strategie-roadmap/SKILL.md"
  [keyword-recherche-cluster]="https://collectivebrain.de/en/skills/keyword-recherche-cluster/SKILL.md"
  [search-console-analyse]="https://collectivebrain.de/en/skills/search-console-analyse/SKILL.md"
  [seo-wettbewerbsanalyse]="https://collectivebrain.de/en/skills/seo-wettbewerbsanalyse/SKILL.md"
  [seo-artikel-schreiben]="https://collectivebrain.de/en/skills/seo-artikel-schreiben/SKILL.md"
  [onpage-optimierung]="https://collectivebrain.de/en/skills/onpage-optimierung/SKILL.md"
  [interne-verlinkung]="https://collectivebrain.de/en/skills/interne-verlinkung/SKILL.md"
  [backlink-kampagne]="https://collectivebrain.de/en/skills/backlink-kampagne/SKILL.md"
  [indexierungs-audit]="https://collectivebrain.de/en/skills/indexierungs-audit/SKILL.md"
  [schema-markup-generator]="https://collectivebrain.de/en/skills/schema-markup-generator/SKILL.md"
  [brand-serp-optimierung]="https://collectivebrain.de/en/skills/brand-serp-optimierung/SKILL.md"
  [local-seo-audit]="https://collectivebrain.de/en/skills/local-seo-audit/SKILL.md"
)
names=("$@"); [ ${#names[@]} -eq 0 ] && names=("${!URL[@]}")
for n in "${names[@]}"; do
  url="${URL[$n]:-}"; [ -n "$url" ] || { echo "unknown skill: $n (see docs/collectivebrain_skills.md)" >&2; continue; }
  mkdir -p "$DIR/$n" && curl -fsSL "$url" -o "$DIR/$n/SKILL.md" && echo "installed $n"
  sleep 1  # be gentle with the site
done
