# Memory System Quick Reference

## Overview
This project uses a three-tiered memory architecture optimized for context budget efficiency across a 14-phase, multi-agent implementation.

## Tier 1: Hot State (CLAUDE.md)
**Purpose**: Current working context loaded in every prompt
**Target Size**: <200 lines (<25KB)
**Update Frequency**: Every session
**Contents**:
- Project Overview (5-10 lines)
- Current State (what's completed, in-progress, planned next)
- Active Issues (open blockers, decisions needed)
- Latest Session Summary (1-2 most recent sessions)
- Import directives to Tier 2 files

**When to Update**:
- After completing a task (move from "In Progress" to "Completed")
- When encountering a blocker (add to "Active Issues")
- After making a decision (one-liner in session summary, full record in decisions-log.md)
- At session end (replace latest session summary, archive old one)

**Size Management**:
- Keep only latest 1-2 session summaries (move older to session-archive.md)
- Keep only active blockers (move resolved to issues-backlog.md)
- Avoid duplicating information already in Tier 2 rules files

## Tier 2: Stable Knowledge (.claude/rules/)
**Purpose**: Configuration and standards that change infrequently
**Target Size**: <100 lines per file
**Update Frequency**: Monthly or when standards change
**Files**:
- stack.md: Dependencies, versions, infrastructure
- architecture.md: Module boundaries, data flow, patterns
- coding-standards.md: Naming, testing, logging conventions
- bloomberg-field-spec.md: 58-field specification, override types, data quality thresholds

**When to Update**:
- When adding new dependencies (stack.md)
- When architectural decisions change module boundaries (architecture.md)
- When coding conventions evolve (coding-standards.md)
- When field requirements change (bloomberg-field-spec.md)

**Import Strategy**:
Files are loaded at session startup via @import directives in CLAUDE.md. Don't duplicate this content in CLAUDE.md.

## Tier 3: Cold Storage (.claude/memory/)
**Purpose**: Detailed history and reference material accessed on-demand
**Update Frequency**: As needed
**Files**:
- decisions-log.md: Full decision records (context, options, rationale, impact)
- session-archive.md: Historical session summaries beyond latest 2
- issues-backlog.md: Resolved issues, known limitations, open questions
- lessons-learned.md: Successful patterns, anti-patterns, what broke and why

**When to Update**:
- After making significant decision (decisions-log.md)
- After resolving issue (issues-backlog.md)
- After discovering pattern or anti-pattern (lessons-learned.md)
- When archiving old session summaries (session-archive.md)

**Read Strategy**:
Only load when relevant to current work. Example: If debugging fiscal period alignment, read lessons-learned.md for known edge cases.

## Update Workflow

### During Active Session
1. Update CLAUDE.md "In Progress" as you work
2. Log decisions immediately (one-liner in CLAUDE.md, full record in decisions-log.md)
3. Flag blockers in "Active Issues"

### Session End
1. Write session summary in CLAUDE.md (replace previous)
2. Move old summary to session-archive.md
3. Update "Completed Work" with session accomplishments
4. Update "Planned Next" with clear next actions
5. Check CLAUDE.md size (if >200 lines, offload content)

### Weekly Maintenance
1. Review "Active Issues" - move resolved to issues-backlog.md
2. Review "In Progress" - remove stale items
3. Check for information drift between CLAUDE.md and rules files

## Agent Handoff Protocol

### When Starting Work
1. Read CLAUDE.md (always loaded)
2. Check relevant rules file(s) based on current phase
3. If working on previously attempted task, read relevant memory file for context

### When Handing Off
1. Update CLAUDE.md with current state
2. Add handoff note to session summary
3. Ensure blockers are clearly documented
4. Log any decisions made

## File Locations
```
/Users/javierlee/Activism Playbook Raw Inputs/raw_inputs/Bloomberg_inputs/
├── CLAUDE.md                           # Tier 1: Hot State
├── .claude/
│   ├── rules/                          # Tier 2: Stable Knowledge
│   │   ├── stack.md
│   │   ├── architecture.md
│   │   ├── coding-standards.md
│   │   └── bloomberg-field-spec.md
│   └── memory/                         # Tier 3: Cold Storage
│       ├── decisions-log.md
│       ├── session-archive.md
│       ├── issues-backlog.md
│       └── lessons-learned.md
```

## Context Budget Math
- CLAUDE.md: ~7KB (153 lines) ✓ Under target
- Rules files: ~10KB total (loaded once per session)
- Memory files: ~15KB total (loaded on-demand)
- Total hot context: <20KB (excellent)
- Available budget: 180KB+ for code/data

## Success Criteria
- CLAUDE.md never exceeds 200 lines
- Any agent can start productive work within first prompt
- No critical context is lost across sessions
- Detailed history accessible when needed
- Agent handoffs are smooth (no information gaps)
