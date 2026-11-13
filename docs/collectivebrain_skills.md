# Collective Brain skills catalogue

All 95 skills listed on [collectivebrain.de/en/skills](https://collectivebrain.de/en/skills/) (Collective Brain, Hamburg), extracted on 13 November 2026, with what each does and where it stands in this repository. The same data is in `collectivebrain_skills.csv` (with install commands and page links).

| Status | Skills | Meaning |
|---|---|---|
| **Added** | 22 | Copied into `.claude/skills/` from the author's open-source repository (MIT or Apache 2.0), reviewed first |
| **In repo** | 2 | Already here from earlier (Superpowers, Caveman) |
| **Built in** | 11 | Part of Claude already (PDF, Word, Excel, PowerPoint, Skill Creator, Cowork, ...) |
| **Install yourself** | 56 | Hosted by Collective Brain, free to use but with no license to republish, so not stored here. Install with `scripts/install_collectivebrain_skills.sh` |
| **Not added** | 4 | Left out for the reason given |

## Design & UX (17)

| Skill | What it does | Author | Status |
|---|---|---|---|
| [Design Critique](https://collectivebrain.de/en/skills/design-design-critique/) | Structured design critique: usability, hierarchy, consistency, accessibility. Honest, but not cynical, like a good senior colleague. | Anthropic | Install yourself: `design-design-critique` |
| [Accessibility Review (WCAG 2.1 AA)](https://collectivebrain.de/en/skills/design-accessibility-review/) | Full WCAG 2.1 AA audit: contrast, keyboard navigation, touch targets, screen readers. Before every launch. | Anthropic | Install yourself: `design-accessibility-review` |
| [UX Copy](https://collectivebrain.de/en/skills/design-ux-copy/) | Microcopy, error messages, empty states, CTAs, written without sounding like marketing. | Anthropic | Install yourself: `design-ux-copy` |
| [User Research Synthesis](https://collectivebrain.de/en/skills/design-research-synthesis/) | Turns 15 interview transcripts into 3 main themes, 5 hypotheses, and a backlog. Instead of 4 hours with sticky notes on a wall. | Anthropic | Install yourself: `design-research-synthesis` |
| [Design Handoff Spec](https://collectivebrain.de/en/skills/design-design-handoff/) | From mockup to dev spec with tokens, component props, interaction states, and edge cases, reliably ready to hand off. | Anthropic | Install yourself: `design-design-handoff` |
| [Design System Audit & Extend](https://collectivebrain.de/en/skills/design-design-system/) | Finds hardcoded values, inconsistent naming patterns, and drift in your design system. Plus: proposes new patterns that fit the architecture. | Anthropic | Install yourself: `design-design-system` |
| [User Research Planning](https://collectivebrain.de/en/skills/design-user-research/) | From research goal to interview guide. Questions that aren't manipulative and answers that are worth something. | Anthropic | Install yourself: `design-user-research` |
| [Anthropic Frontend Design](https://collectivebrain.de/en/skills/anthropic-frontend-design/) | Produces distinctive, production-ready UI layouts instead of generic templates. | Anthropic | Install yourself: `anthropic-frontend-design` |
| [Vercel Web Design Guidelines](https://collectivebrain.de/en/skills/vercel-web-design-guidelines/) | Audits web UIs against more than 100 heuristics covering UX, layout and accessibility. | Vercel Labs | Install yourself: `vercel-web-design-guidelines` |
| [Figma to Code](https://collectivebrain.de/en/skills/figma-to-code/) | Translates Figma frames into clean HTML/CSS or React code with a clear structure. | Collective Brain | Install yourself: `figma-to-code` |
| [Theme Factory](https://collectivebrain.de/en/skills/theme-factory/) | Apply one of 10 curated slide-deck themes (colors, fonts, layout tokens) or generate a custom theme from your brand colors. Palettes and font pairings included inline. | Anthropic | Install yourself: `theme-factory` |
| [UX Flow & Wireframer](https://collectivebrain.de/en/skills/ux-flow-wireframer/) | Sketches user flows and low-fidelity wireframes as text layouts and diagrams. | Community | Install yourself: `ux-flow-wireframer` |
| [Impeccable](https://collectivebrain.de/en/skills/impeccable/) | Impeccable gives Claude Code and other coding agents a design vocabulary: 24 commands to plan, evaluate and refine interfaces, plus a local detector with 62 rules. | Paul Bakaus | Added: `impeccable` |
| [Emil Design Eng](https://collectivebrain.de/en/skills/emil-design-eng/) | The skill helps you build interfaces and animations following Emil Kowalski's design engineering principles and review UI code in a focused way. | emilkowalski | Added: `emil-design-eng` |
| [Review Animations](https://collectivebrain.de/en/skills/review-animations/) | Review Animations checks your animation and motion code against a strict rule set and returns a findings table with a clear Block or Approve decision. | emilkowalski | Added: `review-animations` |
| [shadcn](https://collectivebrain.de/en/skills/shadcn/) | You let Claude add, search, style and fix shadcn/ui components while it follows fixed rules for styling, forms and component structure. | shadcn | Added: `shadcn` |
| [Apple Design](https://collectivebrain.de/en/skills/apple-design/) | Apple Design helps you build and review gesture-driven web interfaces and spring animations based on Apple's motion principles. | emilkowalski | Added: `apple-design` |

## Branding (6)

| Skill | What it does | Author | Status |
|---|---|---|---|
| [Brand Voice Enforcement](https://collectivebrain.de/en/skills/brand-voice-enforcement/) | Automatically applies your brand guidelines to every email, pitch deck, and social post. No more five different voices across the team. | Anthropic | Install yourself: `brand-voice-enforcement` |
| [Brand Voice Guidelines Generator](https://collectivebrain.de/en/skills/brand-voice-guideline-generation/) | Turns sales call transcripts, Notion docs, or a handful of examples into a binding voice guide, in 30 minutes instead of 30 days. | Anthropic | Install yourself: `brand-voice-guideline-generation` |
| [Discover Brand Materials](https://collectivebrain.de/en/skills/brand-voice-discover-brand/) | Autonomously searches Notion, Confluence, Google Drive, Figma, Gong, and Slack for everything that belongs to your brand, and delivers a sorted overview. | Anthropic | Install yourself: `brand-voice-discover-brand` |
| [Brand Review](https://collectivebrain.de/en/skills/marketing-brand-review/) | Before you hit send: does the text fit the brand? Catches brand drift, legal risks and clichés before they go out. | Anthropic | Install yourself: `marketing-brand-review` |
| [Anthropic Brand Application](https://collectivebrain.de/en/skills/anthropic-brand-guidelines/) | Applies Anthropic brand standards to any artifact: colors, typography, visual language. Especially handy when you are building something for or with Anthropic. | Anthropic | Built in |
| [Brandkit](https://collectivebrain.de/en/skills/brandkit/) | Builds complete brand boards with logo ideas, a color world, typography and mockups. | Community | Install yourself: `brandkit` |

## Product (7)

| Skill | What it does | Author | Status |
|---|---|---|---|
| [Vercel React Best Practices](https://collectivebrain.de/en/skills/vercel-react-best-practices/) | Reviews React/Next.js code against performance, DX and UX best practices. | Vercel Labs | Install yourself: `vercel-react-best-practices` |
| [Website Builder (Landing Page Component System)](https://collectivebrain.de/en/skills/website-builder/) | Generates complete landing pages from a component library and deploys them as a WordPress draft. | Community | Install yourself: `website-builder` |
| [UX Research Interview Kit](https://collectivebrain.de/en/skills/ux-research-interview-kit/) | Creates guides, scripts, and evaluation frameworks for structured UX interviews. | Community | Install yourself: `ux-research-interview-kit` |
| [Persona Workshop Facilitator](https://collectivebrain.de/en/skills/persona-workshop-facilitator/) | Helps derive and sharpen B2B personas from research and CRM data. | Community | Install yourself: `persona-workshop-facilitator` |
| [B2B Value Proposition Mapper](https://collectivebrain.de/en/skills/b2b-value-proposition-mapper/) | Structures customer problems, solutions, and proof points into clear value propositions. | Community | Install yourself: `b2b-value-proposition-mapper` |
| [Founder Pitch Deck Coach](https://collectivebrain.de/en/skills/founder-pitch-deck-coach/) | Structures B2B pitch decks and improves the storyline, slides, and graphics. | Community | Install yourself: `founder-pitch-deck-coach` |
| [GitHub Actions: Minuten sparen](https://collectivebrain.de/en/skills/github-actions-sparen/) | Stop blocked deploys and burned CI budget. This skill diagnoses the Actions limit, sets up the right budget, and slims down your workflow (cancel-in-progress, paths-ignore, timeout, fast npm ci). | Collective Brain | Install yourself: `github-actions-sparen` |

## Visual (4)

| Skill | What it does | Author | Status |
|---|---|---|---|
| [Canvas Design](https://collectivebrain.de/en/skills/anthropic-canvas-design/) | PNG and PDF designs grounded in design philosophy: posters, business cards, artwork. Always original, never copied. | Anthropic | Built in |
| [DIVI WordPress Editing](https://collectivebrain.de/en/skills/anthropic-divi-edit/) | Edit, optimize, and migrate DIVI sites: layouts, modules, templates, child themes, performance, and DIVI 5 migration. | Community | Install yourself: `anthropic-divi-edit` |
| [imagegen-frontend-mobile](https://collectivebrain.de/en/skills/imagegen-frontend-mobile/) | Delivers mobile app screens as mockups for convincing product previews. | Community | Install yourself: `imagegen-frontend-mobile` |
| [Algorithmic Art](https://collectivebrain.de/en/skills/algorithmic-art/) | Create standalone generative art with p5.js, from algorithmic philosophy to an interactive viewer. Seeded randomness, flow fields, and particle systems produce reproducible, parametrically controllable works without copying anyone's templates. | Anthropic | Install yourself: `algorithmic-art` |

## AI & Automation (12)

| Skill | What it does | Author | Status |
|---|---|---|---|
| [Skill Creator](https://collectivebrain.de/en/skills/anthropic-skill-creator/) | Creates, improves, and tests your own Claude skills. Includes an eval suite and description optimization for better triggering. | Anthropic | Built in |
| [Create Cowork Plugin](https://collectivebrain.de/en/skills/cowork-create-cowork-plugin/) | Walks you through building your own Cowork plugin, from the first idea to the finished .plugin file. | Anthropic | Built in |
| [Customize Cowork Plugin](https://collectivebrain.de/en/skills/cowork-cowork-plugin-customizer/) | Adapts an existing plugin to your organization's tools, wording, and workflows, without forking the plugin. | Anthropic | Built in |
| [Schedule Tasks](https://collectivebrain.de/en/skills/anthropic-schedule/) | Run recurring tasks automatically: a briefing every morning, a weekly plan every Monday, an inbox check every hour. | Anthropic | Built in |
| [Setup Cowork](https://collectivebrain.de/en/skills/anthropic-setup-cowork/) | Guided onboarding: install role-matched plugins, connect your tools, and try a first skill. | Anthropic | Built in |
| [Google Ads Performance Analyzer](https://collectivebrain.de/en/skills/google-ads-analyzer/) | Analyzes Google Ads data, builds pivot tables, and delivers optimization suggestions. | Community | Install yourself: `google-ads-analyzer` |
| [VopixSounds](https://collectivebrain.de/en/skills/vopixsounds/) | Makes Claude Code audible. One sound when Claude is waiting for your approval or input, a different one when a task is finished. Keep working in another window and never miss the moment Claude needs you. | Vopix | Install yourself: `vopixsounds` |
| [Claude API Referenz](https://collectivebrain.de/en/skills/claude-api/) | Build LLM applications directly against the Anthropic SDK instead of guessing from memory. Current model IDs, pricing, parameters, streaming, tool use, MCP, agents, caching, and token counting in one place. | Anthropic | Install yourself: `claude-api` |
| [MCP Builder](https://collectivebrain.de/en/skills/mcp-builder/) | Build high-quality MCP servers that connect LLMs to external APIs and services through well-designed tools. This skill guides you through research, design, and implementation in Python (FastMCP) or Node/TypeScript (MCP SDK). | Anthropic | Install yourself: `mcp-builder` |
| [Task Observer](https://collectivebrain.de/en/skills/task-observer/) | Watches your Claude sessions and proposes better and new skills from your corrections and patterns. | Eoghan Henn | Not added: Runs during any multi-step task and writes logs to the workspace (CC BY 4.0) |
| [Find Skills](https://collectivebrain.de/en/skills/find-skills/) | You ask about a task, and Claude uses the Skills CLI to search for matching skills, checks install counts and origin, and installs them if you want. | vercel-labs | Not added: Triggers on any 'how do I…' question and installs unvetted third-party skills with npx |
| [Azure AI](https://collectivebrain.de/en/skills/azure-ai/) | You build applications on Azure AI Search, Speech, Azure OpenAI or Document Intelligence and let Claude help with setup, queries and troubleshooting. | microsoft | Added: `azure-ai` |

## Development & Code (16)

| Skill | What it does | Author | Status |
|---|---|---|---|
| [Security Audit](https://collectivebrain.de/en/skills/security-audit/) | You have Claude check codebases, APIs and services for security flaws and get source evidence, a priority and the smallest effective fix for each finding. | cloudflare | Added: `security-audit` |
| [Superpowers](https://collectivebrain.de/en/skills/superpowers/) | Superpowers gives Claude fixed workflows for software projects, from clarifying your requirements through planning and test-driven development to debugging and code review. | obra | In repo |
| [Google Agents CLI ADK Code](https://collectivebrain.de/en/skills/google-agents-cli-adk-code/) | You get a quick reference for Google's Agent Development Kit with code examples in Python and Go. Claude uses it to write agents, tools, callbacks and workflows that follow ADK patterns. | google | Added: `google-agents-cli-adk-code` |
| [Agent Browser](https://collectivebrain.de/en/skills/agent-browser/) | With Agent Browser you let Claude control a Chrome or Chromium browser from the command line to open pages, fill in forms, extract data and test web apps. | vercel-labs | Not added: Tells Claude to prefer it over built-in web tools, but needs a CLI that is not installed |
| [TDD](https://collectivebrain.de/en/skills/mattpocock-tdd/) | You write the failing test before the code: the skill gives Claude rules for the red-green loop, for good tests and for mocking at system boundaries. | mattpocock | Added: `tdd` |
| [Setup Matt Pocock Skills](https://collectivebrain.de/en/skills/setup-matt-pocock-skills/) | You prepare your repository for Matt Pocock's engineering skills in a single run. The skill sets up the issue tracker, triage labels and the location of your glossary and ADRs. | mattpocock | Added: `setup-matt-pocock-skills` |
| [Caveman](https://collectivebrain.de/en/skills/caveman/) | Caveman shortens the output of Claude Code and its subagents, writes terse commit messages and reviews and condenses memory files so your context lasts longer. | juliusbrussee | In repo |
| [TypeScript Advanced Types](https://collectivebrain.de/en/skills/typescript-advanced-types/) | The skill gives Claude explanations and code examples for mapped types, generics, conditional types, utility types and template literal types, so you can implement complex type logic in TypeScript cleanly. | wshobson | Added: `typescript-advanced-types` |
| [Herdr](https://collectivebrain.de/en/skills/herdrdev-herdr/) | With Herdr, you let Claude control panes, tabs and workspaces in the Herdr terminal multiplexer, start other coding agents and check their status. | herdrdev | Added: `herdr` |
| [Google Agents CLI Deploy](https://collectivebrain.de/en/skills/google-agents-cli-deploy/) | You deploy your AI agent with agents-cli to Agent Runtime, Cloud Run or GKE and set up CI/CD, secrets and service accounts along the way. | google | Added: `google-agents-cli-deploy` |
| [playwright-cli](https://collectivebrain.de/en/skills/playwright-cli/) | With playwright-cli you have Claude control a browser through commands, check web pages, simulate network responses and debug Playwright tests from the terminal. | microsoft | Added: `playwright-cli` |
| [Ponytail](https://collectivebrain.de/en/skills/ponytail/) | Ponytail makes Claude build the smallest complete change for coding tasks and checks your changes or your whole repository for bugs, risks and unneeded code. | dietrichgebert | Added: `ponytail` |
| [Turborepo](https://collectivebrain.de/en/skills/turborepo/) | You let Claude set up and debug configuration, caching and CI workflows in your Turborepo monorepo, based on the docs that belong to your turbo version. | vercel | Added: `turborepo` |
| [Google Agents CLI Publish](https://collectivebrain.de/en/skills/google-agents-cli-publish/) | You register an already deployed agent in your Gemini app with agents-cli and manage agents and MCP servers in Agent Registry. | google | Added: `google-agents-cli-publish` |
| [Supabase Postgres Best Practices](https://collectivebrain.de/en/skills/supabase-postgres-best-practices/) | It gives Claude Postgres rules you can rely on when writing SQL, designing schemas, running migrations, writing RLS policies or investigating slow queries. | supabase | Added: `supabase-postgres-best-practices` |
| [Accessibility](https://collectivebrain.de/en/skills/accessibility/) | You let Claude audit your website against WCAG 2.2 and fix the barriers it finds directly in the source code, followed by a fresh check. | addyosmani | Added: `accessibility` |

## Content & Marketing (25)

| Skill | What it does | Author | Status |
|---|---|---|---|
| [Campaign Plan](https://collectivebrain.de/en/skills/marketing-campaign-plan/) | Turns a marketing goal into a 12-week plan with channels, content calendar and dependencies. No spreadsheet lasagna. | Anthropic | Install yourself: `marketing-campaign-plan` |
| [Content Creation](https://collectivebrain.de/en/skills/marketing-content-creation/) | Blog posts, social media, newsletters, landing pages, case studies. Channel-specific, SEO-aware, without the LinkedIn madness. | Anthropic | Install yourself: `marketing-content-creation` |
| [Email Sequence](https://collectivebrain.de/en/skills/marketing-email-sequence/) | Drip sequences with timing, branching, exit conditions, and A/B test suggestions. | Anthropic | Install yourself: `marketing-email-sequence` |
| [SEO Audit](https://collectivebrain.de/en/skills/marketing-seo-audit/) | Keyword gaps, on-page issues, content gaps and a competitor comparison, delivered as a prioritized action list, not an 80-page PDF. | Anthropic | Install yourself: `marketing-seo-audit` |
| [SEO / GEO / AEO Website Audit](https://collectivebrain.de/en/skills/seo-geo-aeo-audit/) | Audits any website across three visibility layers: SEO (Google, Bing), GEO (Perplexity, ChatGPT Search, Gemini, Google AI Overviews) and AEO (featured snippets, voice). Delivers scores plus a prioritized action list as Word and PDF. | SNLabat | Not added: No license in its repository (all rights reserved) |
| [Competitive Brief](https://collectivebrain.de/en/skills/marketing-competitive-brief/) | Five competitors, compared side by side on messaging, visuals, pricing signals and open market niches. | Anthropic | Install yourself: `marketing-competitive-brief` |
| [Performance Report](https://collectivebrain.de/en/skills/marketing-performance-report/) | Translates marketing data into an executive story, with wins, misses and recommendations for the next period. | Anthropic | Install yourself: `marketing-performance-report` |
| [AI Marketing Team](https://collectivebrain.de/en/skills/ai-marketing-team/) | Simulates a small marketing team with roles such as strategist, copywriter and analyst. | Community | Install yourself: `ai-marketing-team` |
| [Keyword Strategy Planner](https://collectivebrain.de/en/skills/keyword-strategy-planner/) | Turns a keyword CSV into a prioritized content and SEO strategy with intent mapping. | Community | Install yourself: `keyword-strategy-planner` |
| [UX Copy Refiner](https://collectivebrain.de/en/skills/ux-copy-refiner/) | Optimizes microcopy for forms, modals, CTAs, and error messages to improve clarity. | Community | Install yourself: `ux-copy-refiner` |
| [Sales Enablement Pack](https://collectivebrain.de/en/skills/sales-enablement-pack/) | Creates one-pagers, battlecards, and objection handling based on product information. | Community | Install yourself: `sales-enablement-pack` |
| [Doc Co-Authoring Workflow](https://collectivebrain.de/en/skills/doc-coauthoring/) | Walks you through a structured workflow for writing documentation together with Claude. You gather context, build each section iteratively, and test at the end whether the text works for real readers. | Anthropic | Install yourself: `doc-coauthoring` |
| [Interne Kommunikation](https://collectivebrain.de/en/skills/internal-comms/) | Write internal communications in the formats your company likes. From status reports and leadership updates to newsletters, FAQs, and incident reports, this skill delivers the right templates and the right tone. | Anthropic | Install yourself: `internal-comms` |
| [SEO Strategy: 90-Day Roadmap](https://collectivebrain.de/en/skills/seo-strategie-roadmap/) | Turns your current SEO situation into a 90-day roadmap with ICE scores, three priorities and a not-doing list for everything that waits until next quarter. | Collective Brain | Install yourself: `seo-strategie-roadmap` |
| [Keyword Research with Topic Clusters](https://collectivebrain.de/en/skills/keyword-recherche-cluster/) | Finds keywords your site can win with the authority it has today, labels them by search intent and groups them into 4 to 6 topic clusters with a pillar article. | Collective Brain | Install yourself: `keyword-recherche-cluster` |
| [Search Console Analysis: Find Quick Wins](https://collectivebrain.de/en/skills/search-console-analyse/) | Reads your GSC export and pulls out striking-distance pages, click losses, CTR outliers and cannibalisation, each with a URL and a fix for this week. | Collective Brain | Install yourself: `search-console-analyse` |
| [SEO Competitive Analysis](https://collectivebrain.de/en/skills/seo-wettbewerbsanalyse/) | Take apart the pages already ranking for your topic and get a content gap map, a keyword steal list and the three pages to write first. | Collective Brain | Install yourself: `seo-wettbewerbsanalyse` |
| [Write SEO Articles](https://collectivebrain.de/en/skills/seo-artikel-schreiben/) | Get a finished SEO article with title tag, meta description, FAQ and internal links, built from the live SERP and written without AI stock phrases. | Collective Brain | Install yourself: `seo-artikel-schreiben` |
| [On-Page Optimisation for Existing Pages](https://collectivebrain.de/en/skills/onpage-optimierung/) | Hand over an existing URL and a target keyword, get finished rewrites for title, meta, headings and intro, plus content gaps and a schema recommendation. | Collective Brain | Install yourself: `onpage-optimierung` |
| [Plan Internal Linking](https://collectivebrain.de/en/skills/interne-verlinkung/) | Finds orphan pages, unused authority pages and broken topic clusters. You get a link plan with exact anchor text and placement in every row, not a pile of advice. | Collective Brain | Install yourself: `interne-verlinkung` |
| [Set Up a Backlink Campaign](https://collectivebrain.de/en/skills/backlink-kampagne/) | Plans a clean link campaign across five prospect categories and ships the outreach mails with it. No PBNs, no paid links, no tactics that risk a manual action. | Collective Brain | Install yourself: `backlink-kampagne` |
| [Indexing Audit](https://collectivebrain.de/en/skills/indexierungs-audit/) | Sorts your URLs into keep, deindex, consolidate and missing. Every finding comes with the ready directive: noindex, robots.txt rule, canonical or 301. | Collective Brain | Install yourself: `indexierungs-audit` |
| [Generate Schema Markup](https://collectivebrain.de/en/skills/schema-markup-generator/) | You get valid JSON-LD for a specific page, matched against its visible content, plus a list of every placeholder and the warnings the Rich Results Test will raise. | Collective Brain | Install yourself: `schema-markup-generator` |
| [Optimize Your Brand SERP](https://collectivebrain.de/en/skills/brand-serp-optimierung/) | You see what Google serves for your brand name, how much of it you control, and which five measures improve the brand SERP fastest. | Collective Brain | Install yourself: `brand-serp-optimierung` |
| [Local SEO Audit](https://collectivebrain.de/en/skills/local-seo-audit/) | You check Google Business Profile, NAP consistency, reviews and location pages in one pass and get the five fixes with the best impact-to-effort ratio. | Collective Brain | Install yourself: `local-seo-audit` |

## Office & Data (8)

| Skill | What it does | Author | Status |
|---|---|---|---|
| [PDF Workflows](https://collectivebrain.de/en/skills/anthropic-pdf/) | Create, read, merge, split, OCR and fill out forms in PDFs, without an Adobe subscription. | Anthropic | Built in |
| [Word Document Creation](https://collectivebrain.de/en/skills/anthropic-docx/) | Word documents with a table of contents, headers, page numbers and a letterhead, generated programmatically. | Anthropic | Built in |
| [Excel Spreadsheets](https://collectivebrain.de/en/skills/anthropic-xlsx/) | Read and write Excel files, with formulas and charts. Even for the spreadsheets nobody wants to clean up anymore. | Anthropic | Built in |
| [PowerPoint Presentations](https://collectivebrain.de/en/skills/anthropic-pptx/) | Slide decks from an outline, data, or a story. With layouts, speaker notes, and on-brand charts, ready for the pitch. | Anthropic | Built in |
| [Notion Ops Connector](https://collectivebrain.de/en/skills/notion-ops-connector/) | Reads and updates Notion databases for content plans, roadmaps, and wikis. | Community | Install yourself: `notion-ops-connector` |
| [Obsidian Markdown](https://collectivebrain.de/en/skills/obsidian-markdown/) | You let Claude create and edit notes for Obsidian, using wikilinks, embeds, callouts, tags and frontmatter properties in valid syntax. | kepano | Added: `obsidian-markdown` |
| [Obsidian Bases](https://collectivebrain.de/en/skills/obsidian-bases/) | You let Claude create and edit Bases in Obsidian: filters, computed formulas, summaries and views as a table, cards, list or map. | kepano | Added: `obsidian-bases` |
| [lark-im](https://collectivebrain.de/en/skills/lark-im/) | With lark-im you send and reply to Lark messages through Claude, search chat history, manage group chats and download files from conversations. | larksuite | Added: `lark-im` |

## Notes

- **Licenses**: the 22 added skills keep their license files; their repositories and commits are listed in `SKILLS.md`. Collective Brain's own pages give no license for the files it hosts, and a few of those are condensed versions of Anthropic skills.
- **Checked before listing**: all 56 hosted files were downloaded and scanned; none contains shell pipes to remote scripts, destructive commands, credential access or instructions to override the user.
- **Token cost**: Claude reads every installed skill's description at the start of each session (roughly 30-150 tokens each), so install the hosted ones you will actually use rather than all 56.
