---
type: table
title: rep_course_flags
resource: d2.rep_course_flags
tags: [schema]
---
# Table: `rep_course_flags`

| field | type | meaning |
|---|---|---|
| `completed_advneg` | bool | TRUE if the rep completed the 'Advanced Negotiation' course. Resolved via the certified identity bridge. (expression: `rep_course_flags.completed_advneg`) |
| `completed_distract` | bool | TRUE if the rep completed 'Intro to Spreadsheets' (a control/placebo course). (expression: `rep_course_flags.completed_distract`) |
